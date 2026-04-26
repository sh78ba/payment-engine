"""
Concurrency test for the payout engine.

This is the most critical test: two simultaneous 60-rupee payout requests
against a 100-rupee balance. Exactly one must succeed, the other must fail.

We use Python threads + Django's TransactionTestCase (which uses real DB
transactions, not savepoints) to exercise the actual SELECT FOR UPDATE lock.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from django.test import TransactionTestCase
from django.db import connection

from payouts.models import Merchant, BankAccount, LedgerEntry, Payout
from payouts.services.payout import create_payout, InsufficientBalanceError
from payouts.services.ledger import get_merchant_balance


class ConcurrentPayoutTest(TransactionTestCase):
    """
    Tests that concurrent payout requests are properly serialized by
    the database-level SELECT FOR UPDATE lock.
    """

    def setUp(self):
        """Create a merchant with ₹100 (10000 paise) balance."""
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
        # Seed ₹100 (10000 paise)
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount_paise=10000,
            description="Test credit",
        )

    def _run_concurrent_payouts(self, num_threads, amount_paise):
        """
        Helper: runs num_threads concurrent payout attempts.
        Returns a list of (result_type, detail) tuples.
        Uses a Barrier to synchronize thread start for max collision.
        """
        barrier = threading.Barrier(num_threads, timeout=10)
        results = []  # Populated after join, so thread-safe
        lock = threading.Lock()

        def attempt_payout():
            # Each thread must have its own DB connection
            connection.close()
            try:
                barrier.wait()
                payout = create_payout(
                    merchant_id=self.merchant.id,
                    amount_paise=amount_paise,
                    bank_account_id=self.bank_account.id,
                )
                with lock:
                    results.append(("success", str(payout.id)))
            except InsufficientBalanceError as e:
                with lock:
                    results.append(("insufficient", str(e)))
            except Exception as e:
                with lock:
                    results.append(("error", str(e)))

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(attempt_payout) for _ in range(num_threads)]
            for f in futures:
                f.result(timeout=15)

        return results

    def test_concurrent_payouts_no_overdraw(self):
        """
        Two threads submit 6000 paise (₹60) payouts simultaneously.
        Merchant has 10000 paise (₹100).
        Only one should succeed. The other must get InsufficientBalanceError.

        This test exercises the SELECT FOR UPDATE lock in create_payout().
        Without the lock, both threads would read balance=10000, both would
        proceed, and the merchant would be overdrawn by 2000 paise.
        """
        results = self._run_concurrent_payouts(num_threads=2, amount_paise=6000)

        successes = [r for r in results if r[0] == "success"]
        insufficients = [r for r in results if r[0] == "insufficient"]
        errors = [r for r in results if r[0] == "error"]

        # Exactly one success, one failure
        self.assertEqual(
            len(successes), 1,
            f"Expected 1 success, got {len(successes)}. All results: {results}",
        )
        self.assertEqual(
            len(insufficients), 1,
            f"Expected 1 insufficient, got {len(insufficients)}. All results: {results}",
        )
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

        # Verify final balance integrity
        final_balance = get_merchant_balance(self.merchant.id)
        self.assertEqual(
            final_balance, 4000,
            f"Balance integrity violation! Expected 4000, got {final_balance}",
        )

        # Verify only one payout was created
        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 1, f"Expected 1 payout, got {payout_count}")

        # Verify only one debit ledger entry
        debit_count = LedgerEntry.objects.filter(
            merchant=self.merchant,
            entry_type=LedgerEntry.EntryType.DEBIT,
        ).count()
        self.assertEqual(debit_count, 1, f"Expected 1 debit entry, got {debit_count}")

    def test_concurrent_payouts_both_within_balance(self):
        """
        Two threads submit 4000 paise (₹40) payouts simultaneously.
        Merchant has 10000 paise (₹100).
        Both should succeed since total (8000) is within balance.
        """
        results = self._run_concurrent_payouts(num_threads=2, amount_paise=4000)

        successes = [r for r in results if r[0] == "success"]
        errors = [r for r in results if r[0] == "error"]

        self.assertEqual(
            len(successes), 2,
            f"Expected 2 successes, got {len(successes)}. All results: {results}",
        )
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

        # Final balance = 10000 - 4000 - 4000 = 2000
        final_balance = get_merchant_balance(self.merchant.id)
        self.assertEqual(final_balance, 2000)

    def test_balance_never_goes_negative(self):
        """
        Stress test: 5 threads each try to withdraw the full balance.
        Only one should succeed.
        """
        results = self._run_concurrent_payouts(num_threads=5, amount_paise=10000)

        successes = [r for r in results if r[0] == "success"]
        insufficients = [r for r in results if r[0] == "insufficient"]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(insufficients), 4)

        # Balance should be exactly 0
        self.assertEqual(get_merchant_balance(self.merchant.id), 0)
