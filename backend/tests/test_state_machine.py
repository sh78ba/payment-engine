"""
State machine test for payout transitions.
Verifies that illegal transitions are blocked.
"""

from django.test import TransactionTestCase

from payouts.models import Merchant, BankAccount, LedgerEntry, Payout


class StateMachineTest(TransactionTestCase):
    """Tests that the payout state machine enforces legal transitions."""

    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Test Merchant",
            email="test@statemachine.com",
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number="1234567890",
            ifsc_code="TEST0001234",
            account_holder_name="Test User",
            bank_name="Test Bank",
        )

    def _create_payout(self, status=Payout.Status.PENDING):
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account=self.bank_account,
            amount_paise=1000,
            status=status,
        )
        return payout

    def test_pending_to_processing(self):
        """PENDING -> PROCESSING is legal."""
        payout = self._create_payout(Payout.Status.PENDING)
        payout.transition_to(Payout.Status.PROCESSING)
        self.assertEqual(payout.status, Payout.Status.PROCESSING)

    def test_processing_to_completed(self):
        """PROCESSING -> COMPLETED is legal."""
        payout = self._create_payout(Payout.Status.PROCESSING)
        payout.transition_to(Payout.Status.COMPLETED)
        self.assertEqual(payout.status, Payout.Status.COMPLETED)

    def test_processing_to_failed(self):
        """PROCESSING -> FAILED is legal."""
        payout = self._create_payout(Payout.Status.PROCESSING)
        payout.transition_to(Payout.Status.FAILED)
        self.assertEqual(payout.status, Payout.Status.FAILED)

    def test_completed_to_pending_blocked(self):
        """COMPLETED -> PENDING is ILLEGAL."""
        payout = self._create_payout(Payout.Status.COMPLETED)
        with self.assertRaises(ValueError) as ctx:
            payout.transition_to(Payout.Status.PENDING)
        self.assertIn("Illegal state transition", str(ctx.exception))
        self.assertIn("COMPLETED -> PENDING", str(ctx.exception))

    def test_failed_to_completed_blocked(self):
        """FAILED -> COMPLETED is ILLEGAL. This is the specific check the spec asks about."""
        payout = self._create_payout(Payout.Status.FAILED)
        with self.assertRaises(ValueError) as ctx:
            payout.transition_to(Payout.Status.COMPLETED)
        self.assertIn("Illegal state transition", str(ctx.exception))

    def test_completed_to_failed_blocked(self):
        """COMPLETED -> FAILED is ILLEGAL."""
        payout = self._create_payout(Payout.Status.COMPLETED)
        with self.assertRaises(ValueError) as ctx:
            payout.transition_to(Payout.Status.FAILED)
        self.assertIn("Illegal state transition", str(ctx.exception))

    def test_pending_to_completed_blocked(self):
        """PENDING -> COMPLETED is ILLEGAL (must go through PROCESSING)."""
        payout = self._create_payout(Payout.Status.PENDING)
        with self.assertRaises(ValueError) as ctx:
            payout.transition_to(Payout.Status.COMPLETED)
        self.assertIn("Illegal state transition", str(ctx.exception))

    def test_failed_to_processing_blocked(self):
        """FAILED -> PROCESSING is ILLEGAL."""
        payout = self._create_payout(Payout.Status.FAILED)
        with self.assertRaises(ValueError) as ctx:
            payout.transition_to(Payout.Status.PROCESSING)
        self.assertIn("Illegal state transition", str(ctx.exception))
