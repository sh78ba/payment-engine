"""
Ledger service: all balance calculations happen here, always via DB aggregation.

This is the ONLY place where balance is computed. No Python arithmetic on fetched rows.
Every query uses Django's ORM aggregation which translates to SQL SUM/CASE expressions.

Balance model:
- Total balance = SUM(credits) + SUM(refunds) - SUM(debits)
  This already accounts for ALL money movements including holds.
- Held balance = SUM(debits WHERE payout is PENDING or PROCESSING)
  This is how much of the total is "locked" in in-flight payouts.
- Available balance = total - held
  This is what the merchant can still withdraw.

IMPORTANT: When a payout is created, a DEBIT entry is created immediately.
This DEBIT reduces the total balance. The DEBIT amount also appears in the
held balance. Available = total - held correctly gives us the withdrawable
amount because:
  - total already subtracted the DEBIT
  - held RE-ADDS the DEBIT (since it's "locked but not gone yet")
  - available = total - held ... wait, that double-subtracts.

Actually, the correct model is:
  available = SUM(credits) + SUM(refunds) - SUM(debits where payout is COMPLETED)
  held = SUM(debits where payout is PENDING or PROCESSING)
  total = available + held  (informational, equals SUM(credits) + SUM(refunds) - SUM(all debits) + held)

We compute available directly, not as total - held, to avoid confusion.
"""

from django.db import models
from django.db.models import Sum, Case, When, Value, BigIntegerField, Q
from payouts.models import LedgerEntry, Payout


def get_merchant_balance(merchant_id):
    """
    Compute the merchant's TOTAL net balance from ledger entries.
    This is credits + refunds - ALL debits (including pending/processing ones).

    SQL equivalent:
        SELECT COALESCE(
            SUM(CASE
                WHEN entry_type IN ('CREDIT', 'REFUND') THEN amount_paise
                WHEN entry_type = 'DEBIT' THEN -amount_paise
                ELSE 0
            END), 0
        ) AS total_balance
        FROM ledger_entries
        WHERE merchant_id = %s

    Returns: int (paise)
    """
    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total=Sum(
            Case(
                When(
                    entry_type__in=[
                        LedgerEntry.EntryType.CREDIT,
                        LedgerEntry.EntryType.REFUND,
                    ],
                    then="amount_paise",
                ),
                When(
                    entry_type=LedgerEntry.EntryType.DEBIT,
                    then=models.F("amount_paise") * -1,
                ),
                default=Value(0),
                output_field=BigIntegerField(),
            )
        )
    )
    return result["total"] or 0


def get_held_balance(merchant_id):
    """
    Compute the merchant's held balance: sum of debit amounts for payouts
    that are still in PENDING or PROCESSING state.

    These funds are "locked" — they've been deducted from total but haven't
    settled yet (not completed, not failed/refunded).

    SQL equivalent:
        SELECT COALESCE(SUM(le.amount_paise), 0)
        FROM ledger_entries le
        JOIN payouts p ON le.payout_id = p.id
        WHERE le.merchant_id = %s
          AND le.entry_type = 'DEBIT'
          AND p.status IN ('PENDING', 'PROCESSING')

    Returns: int (paise)
    """
    result = LedgerEntry.objects.filter(
        merchant_id=merchant_id,
        entry_type=LedgerEntry.EntryType.DEBIT,
        payout__status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING],
    ).aggregate(total=Sum("amount_paise"))
    return result["total"] or 0


def get_available_balance(merchant_id):
    """
    Available balance: the amount the merchant can request as a NEW payout.

    Formula: SUM(credits) + SUM(refunds) - SUM(debits for COMPLETED payouts)
                                          - SUM(debits for PENDING/PROCESSING payouts)

    This equals get_merchant_balance() because total already subtracts ALL debits.

    We use get_merchant_balance() directly because:
    - A DEBIT entry is created when a payout is created (holds funds)
    - A REFUND entry is created when a payout fails (returns funds)
    - A COMPLETED payout's DEBIT stays (funds permanently gone)
    - So total = credits + refunds - all debits = what's truly available + 0
      (held funds are already subtracted from total via their DEBIT entries)

    Returns: int (paise)
    """
    return get_merchant_balance(merchant_id)


def get_total_credits(merchant_id):
    """Total credits received by merchant."""
    result = LedgerEntry.objects.filter(
        merchant_id=merchant_id,
        entry_type=LedgerEntry.EntryType.CREDIT,
    ).aggregate(total=Sum("amount_paise"))
    return result["total"] or 0


def get_total_debits(merchant_id):
    """Total debits (for completed/settled payouts) for merchant."""
    result = LedgerEntry.objects.filter(
        merchant_id=merchant_id,
        entry_type=LedgerEntry.EntryType.DEBIT,
        payout__status=Payout.Status.COMPLETED,
    ).aggregate(total=Sum("amount_paise"))
    return result["total"] or 0
