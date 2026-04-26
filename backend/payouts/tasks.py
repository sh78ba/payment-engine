"""
Celery tasks for the Payout Processor.

These tasks run as background workers and handle:
1. Processing PENDING payouts (moving them through the lifecycle)
2. Retrying PROCESSING payouts that are stuck (> 30 seconds)
3. Cleaning up expired idempotency keys

Bank settlement is simulated:
- 70% succeed
- 20% fail
- 10% hang (remain in PROCESSING for retry)
"""

import random
import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from payouts.models import Payout, LedgerEntry

logger = logging.getLogger(__name__)


def simulate_bank_settlement():
    """
    Simulate bank API response.
    Returns: 'success', 'failure', or 'processing' (hang)
    """
    roll = random.random()
    if roll < 0.7:
        return "success"
    elif roll < 0.9:
        return "failure"
    else:
        return "processing"  # Simulates a hang


@shared_task(name="payouts.tasks.process_pending_payouts")
def process_pending_payouts():
    """
    Pick up all PENDING payouts and attempt to process them.

    For each payout:
    1. Transition to PROCESSING (with optimistic locking via DB WHERE clause)
    2. Simulate bank settlement
    3. On success: transition to COMPLETED
    4. On failure: transition to FAILED and atomically refund the held amount
    5. On hang: leave in PROCESSING (retry task will handle it)
    """
    pending_payouts = Payout.objects.filter(
        status=Payout.Status.PENDING
    ).select_for_update(skip_locked=True)

    with transaction.atomic():
        payout_ids = list(pending_payouts.values_list("id", flat=True))

    for payout_id in payout_ids:
        process_single_payout.delay(str(payout_id))


@shared_task(name="payouts.tasks.process_single_payout")
def process_single_payout(payout_id):
    """
    Process a single payout through the bank settlement simulation.
    Each payout is processed in its own task for isolation.
    """
    try:
        with transaction.atomic():
            # Lock the payout row to prevent concurrent processing
            payout = Payout.objects.select_for_update().get(id=payout_id)

            # Only process if still PENDING
            if payout.status != Payout.Status.PENDING:
                logger.info(
                    f"Payout {payout_id} is no longer PENDING (status={payout.status}), skipping"
                )
                return

            # Transition to PROCESSING
            payout.transition_to(Payout.Status.PROCESSING)
            payout.attempt_count += 1
            payout.last_attempted_at = timezone.now()
            payout.save()

        # Simulate bank API call (outside the transaction to not hold locks)
        result = simulate_bank_settlement()
        logger.info(f"Payout {payout_id} bank result: {result}")

        if result == "success":
            _complete_payout(payout_id)
        elif result == "failure":
            _fail_payout(payout_id)
        else:
            # "processing" - leave it, retry task will pick it up
            logger.info(f"Payout {payout_id} is hanging in PROCESSING state")

    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found")
    except ValueError as e:
        logger.error(f"State transition error for payout {payout_id}: {e}")


def _complete_payout(payout_id):
    """
    Mark payout as COMPLETED.
    The debit ledger entry remains - funds are permanently deducted.
    """
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if payout.status != Payout.Status.PROCESSING:
            logger.warning(
                f"Cannot complete payout {payout_id}: status is {payout.status}"
            )
            return

        payout.transition_to(Payout.Status.COMPLETED)
        payout.save()
        logger.info(f"Payout {payout_id} COMPLETED successfully")


def _fail_payout(payout_id):
    """
    Mark payout as FAILED and atomically return held funds.

    CRITICAL: The state transition and the refund ledger entry MUST be
    in the same transaction. If we fail the payout but don't refund,
    or refund but don't fail, the ledger is inconsistent.
    """
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if payout.status != Payout.Status.PROCESSING:
            logger.warning(
                f"Cannot fail payout {payout_id}: status is {payout.status}"
            )
            return

        # Atomic: transition to FAILED + create refund entry
        payout.transition_to(Payout.Status.FAILED)
        payout.save()

        # Return the held funds via a REFUND ledger entry
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            entry_type=LedgerEntry.EntryType.REFUND,
            amount_paise=payout.amount_paise,
            description=f"Payout failed - refund for {payout.id}",
            payout=payout,
        )

        logger.info(
            f"Payout {payout_id} FAILED. Refunded {payout.amount_paise} paise"
        )


@shared_task(name="payouts.tasks.retry_stuck_payouts")
def retry_stuck_payouts():
    """
    Find payouts stuck in PROCESSING state for longer than the configured timeout.

    Retry logic:
    - If attempt_count < max_attempts: reset to PENDING for reprocessing
      (uses exponential backoff: only retry if stuck for timeout * 2^attempt)
    - If attempt_count >= max_attempts: fail the payout and return funds

    The timeout and max attempts are configurable via settings:
    - PAYOUT_PROCESSING_TIMEOUT_SECONDS (default: 30)
    - PAYOUT_RETRY_MAX_ATTEMPTS (default: 3)
    """
    timeout_seconds = getattr(settings, "PAYOUT_PROCESSING_TIMEOUT_SECONDS", 30)
    max_attempts = getattr(settings, "PAYOUT_RETRY_MAX_ATTEMPTS", 3)

    stuck_payouts = Payout.objects.filter(
        status=Payout.Status.PROCESSING,
        last_attempted_at__isnull=False,
    )

    for payout in stuck_payouts:
        # Exponential backoff: timeout * 2^(attempt_count - 1)
        backoff_timeout = timeout_seconds * (2 ** (payout.attempt_count - 1))
        time_in_processing = (
            timezone.now() - payout.last_attempted_at
        ).total_seconds()

        if time_in_processing < backoff_timeout:
            continue  # Not yet timed out for this attempt level

        if payout.attempt_count >= max_attempts:
            # Max retries exhausted - fail the payout
            logger.warning(
                f"Payout {payout.id} exhausted {max_attempts} attempts. Failing."
            )
            _fail_payout(str(payout.id))
        else:
            # Retry: move back to PENDING
            logger.info(
                f"Payout {payout.id} stuck for {time_in_processing:.0f}s "
                f"(attempt {payout.attempt_count}/{max_attempts}). Retrying."
            )
            with transaction.atomic():
                p = Payout.objects.select_for_update().get(id=payout.id)
                if p.status == Payout.Status.PROCESSING:
                    # We bypass the state machine here intentionally for retry.
                    # This is the ONLY place where PROCESSING -> PENDING is allowed.
                    p.status = Payout.Status.PENDING
                    p.save()


@shared_task(name="payouts.tasks.cleanup_expired_idempotency_keys")
def cleanup_expired_idempotency_keys():
    """Delete idempotency keys older than the configured TTL."""
    from payouts.models import IdempotencyKey

    ttl_hours = getattr(settings, "IDEMPOTENCY_KEY_TTL_HOURS", 24)
    cutoff = timezone.now() - timedelta(hours=ttl_hours)

    deleted_count, _ = IdempotencyKey.objects.filter(created_at__lt=cutoff).delete()
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired idempotency keys")
