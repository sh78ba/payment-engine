"""
Idempotency test for the payout engine.

Verifies that:
1. Second call with the same idempotency key returns the same response
2. No duplicate payout is created
3. Expired keys are treated as new keys
4. Keys are scoped per merchant
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from payouts.models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey
from payouts.services.payout import (
    handle_idempotent_payout,
    InsufficientBalanceError,
    DuplicateIdempotencyKeyError,
)
from payouts.services.ledger import get_available_balance


class IdempotencyTest(TransactionTestCase):
    """Tests for idempotency key handling in payout creation."""

    def setUp(self):
        """Create a merchant with ₹500 (50000 paise) balance."""
        self.merchant = Merchant.objects.create(
            name="Test Merchant",
            email="test@merchant.com",
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number="1234567890",
            ifsc_code="TEST0001234",
            account_holder_name="Test User",
            bank_name="Test Bank",
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount_paise=50000,
            description="Test credit",
        )

    def test_duplicate_key_returns_same_response(self):
        """
        Calling handle_idempotent_payout twice with the same key should:
        - Return the same response body both times
        - Create only ONE payout
        - Only debit the balance ONCE
        """
        key = str(uuid.uuid4())
        amount = 10000  # ₹100

        # First call
        body1, status1, is_replay1 = handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=amount,
            bank_account_id=self.bank_account.id,
            idempotency_key=key,
        )

        self.assertEqual(status1, 201)
        self.assertFalse(is_replay1)

        # Second call - same key
        body2, status2, is_replay2 = handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=amount,
            bank_account_id=self.bank_account.id,
            idempotency_key=key,
        )

        self.assertEqual(status2, 201)
        self.assertTrue(is_replay2)  # Should be marked as replay

        # Responses must be identical
        self.assertEqual(body1["id"], body2["id"])
        self.assertEqual(body1["amount_paise"], body2["amount_paise"])

        # Only ONE payout should exist
        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 1)

        # Balance should reflect only ONE debit
        available = get_available_balance(self.merchant.id)
        self.assertEqual(available, 40000)  # 50000 - 10000

    def test_different_keys_create_different_payouts(self):
        """Different idempotency keys should create separate payouts."""
        key1 = str(uuid.uuid4())
        key2 = str(uuid.uuid4())

        handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=10000,
            bank_account_id=self.bank_account.id,
            idempotency_key=key1,
        )
        handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=10000,
            bank_account_id=self.bank_account.id,
            idempotency_key=key2,
        )

        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 2)

    def test_expired_key_treated_as_new(self):
        """
        An expired idempotency key (> 24 hours old) should be treated as
        a new request, creating a new payout.
        """
        key = str(uuid.uuid4())

        # First call
        handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=5000,
            bank_account_id=self.bank_account.id,
            idempotency_key=key,
        )

        # Expire the key by backdating it
        IdempotencyKey.objects.filter(
            merchant=self.merchant, key=key
        ).update(created_at=timezone.now() - timedelta(hours=25))

        # Second call with same key should create a new payout
        body2, status2, is_replay2 = handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=5000,
            bank_account_id=self.bank_account.id,
            idempotency_key=key,
        )

        self.assertEqual(status2, 201)
        self.assertFalse(is_replay2)

        # Two payouts should exist now
        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 2)

    def test_keys_scoped_per_merchant(self):
        """
        Same idempotency key used by different merchants should create
        separate payouts for each.
        """
        merchant2 = Merchant.objects.create(
            name="Other Merchant",
            email="other@merchant.com",
        )
        bank2 = BankAccount.objects.create(
            merchant=merchant2,
            account_number="0000000000",
            ifsc_code="TEST0000000",
            account_holder_name="Other User",
            bank_name="Other Bank",
        )
        LedgerEntry.objects.create(
            merchant=merchant2,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount_paise=50000,
            description="Test credit",
        )

        key = str(uuid.uuid4())

        # Same key, different merchants
        handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=5000,
            bank_account_id=self.bank_account.id,
            idempotency_key=key,
        )
        handle_idempotent_payout(
            merchant_id=merchant2.id,
            amount_paise=5000,
            bank_account_id=bank2.id,
            idempotency_key=key,
        )

        # Each merchant should have their own payout
        self.assertEqual(
            Payout.objects.filter(merchant=self.merchant).count(), 1
        )
        self.assertEqual(
            Payout.objects.filter(merchant=merchant2).count(), 1
        )

    def test_failed_request_replays_error(self):
        """
        If the first request failed (e.g., insufficient balance),
        replaying the same key should return the same error.
        """
        key = str(uuid.uuid4())

        # Try to withdraw more than available
        with self.assertRaises(InsufficientBalanceError):
            handle_idempotent_payout(
                merchant_id=self.merchant.id,
                amount_paise=999999999,  # Way more than balance
                bank_account_id=self.bank_account.id,
                idempotency_key=key,
            )

        # Replay should return stored error
        body, status_code, is_replay = handle_idempotent_payout(
            merchant_id=self.merchant.id,
            amount_paise=999999999,
            bank_account_id=self.bank_account.id,
            idempotency_key=key,
        )

        self.assertTrue(is_replay)
        self.assertEqual(status_code, 422)
        self.assertIn("error", body)
