"""
Payout service: handles payout creation with concurrency control and idempotency.

Key design:
- Uses SELECT FOR UPDATE on the Merchant row to serialize concurrent payout requests.
- Balance check happens INSIDE the transaction, after acquiring the lock.
- Debit ledger entry is created atomically with the payout.
"""

import json
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.utils import timezone
from django.conf import settings
from rest_framework.utils.encoders import JSONEncoder

from payouts.models import Merchant, BankAccount, Payout, LedgerEntry, IdempotencyKey
from payouts.services.ledger import get_available_balance


class InsufficientBalanceError(Exception):
    pass


class InvalidBankAccountError(Exception):
    pass


class DuplicateIdempotencyKeyError(Exception):
    """Raised when a duplicate idempotency key is still being processed."""
    pass


def create_payout(merchant_id, amount_paise, bank_account_id, idempotency_key=None):
    """
    Create a payout request with full concurrency protection.

    The critical section:
    1. Acquire row-level lock on Merchant via SELECT FOR UPDATE
    2. Compute available balance via DB aggregation (inside the same transaction)
    3. If sufficient, create Payout + Debit LedgerEntry atomically
    4. Release lock on commit

    Two concurrent requests for the same merchant will be serialized by the
    database lock. The second request will see the updated balance (including
    the first request's debit) and be rejected if insufficient.

    Args:
        merchant_id: UUID of the merchant
        amount_paise: int, amount in paise (must be positive)
        bank_account_id: UUID of the bank account
        idempotency_key: optional string, merchant-supplied UUID

    Returns:
        Payout instance

    Raises:
        InsufficientBalanceError: if available balance < amount_paise
        InvalidBankAccountError: if bank account doesn't belong to merchant
        Merchant.DoesNotExist: if merchant not found
    """
    if amount_paise <= 0:
        raise ValueError("Payout amount must be positive")

    # Use a single atomic transaction with row-level locking
    with transaction.atomic():
        # STEP 1: Acquire exclusive lock on the merchant row.
        # SELECT ... FOR UPDATE prevents any other transaction from reading
        # this row until we commit. This serializes all concurrent payout
        # requests for the same merchant.
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # STEP 2: Validate bank account belongs to this merchant
        try:
            bank_account = BankAccount.objects.get(
                id=bank_account_id, merchant=merchant
            )
        except BankAccount.DoesNotExist:
            raise InvalidBankAccountError(
                f"Bank account {bank_account_id} does not belong to merchant {merchant_id}"
            )

        # STEP 3: Compute available balance INSIDE the transaction.
        # Because we hold the FOR UPDATE lock, no other transaction can
        # create new ledger entries for this merchant until we commit.
        available = get_available_balance(merchant_id)

        if available < amount_paise:
            raise InsufficientBalanceError(
                f"Insufficient balance. Available: {available} paise, "
                f"Requested: {amount_paise} paise"
            )

        # STEP 4: Create the payout
        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.Status.PENDING,
        )

        # STEP 5: Create the debit ledger entry (holds the funds)
        LedgerEntry.objects.create(
            merchant=merchant,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount_paise=amount_paise,
            description=f"Payout hold - {payout.id}",
            payout=payout,
        )

    # Transaction committed - lock released, funds held
    return payout


def handle_idempotent_payout(merchant_id, amount_paise, bank_account_id, idempotency_key):
    """
    Wraps create_payout with idempotency key handling.

    Flow:
    1. Check if key exists and is not expired
       - If exists and completed: return stored response (replay)
       - If exists and still processing: raise DuplicateIdempotencyKeyError
    2. If key doesn't exist: create it, process payout, store response
    3. On any error: mark key as completed with error response

    The unique constraint on (merchant_id, key) prevents race conditions
    where two concurrent requests with the same key both try to insert.
    The loser of the INSERT race gets an IntegrityError and retries the lookup.
    """
    ttl_hours = getattr(settings, "IDEMPOTENCY_KEY_TTL_HOURS", 24)
    expiry_cutoff = timezone.now() - timedelta(hours=ttl_hours)

    # Check for existing non-expired key
    existing = IdempotencyKey.objects.filter(
        merchant_id=merchant_id,
        key=idempotency_key,
        created_at__gte=expiry_cutoff,
    ).first()

    if existing:
        if not existing.is_processing:
            # Request already completed - replay the stored response
            return existing.response_body, existing.response_status_code, True
        else:
            # First request is still in flight
            raise DuplicateIdempotencyKeyError(
                "A request with this idempotency key is currently being processed"
            )

    # Clean up any expired keys for this merchant+key combo so the
    # unique constraint doesn't block reuse of expired keys
    IdempotencyKey.objects.filter(
        merchant_id=merchant_id,
        key=idempotency_key,
        created_at__lt=expiry_cutoff,
    ).delete()

    # Try to create the idempotency key record
    try:
        with transaction.atomic():
            idem_record = IdempotencyKey.objects.create(
                merchant_id=merchant_id,
                key=idempotency_key,
                is_processing=True,
            )
    except IntegrityError:
        # Another concurrent request created the key first.
        # Look it up and return its response or signal conflict.
        existing = IdempotencyKey.objects.filter(
            merchant_id=merchant_id,
            key=idempotency_key,
            created_at__gte=expiry_cutoff,
        ).first()
        if existing and not existing.is_processing:
            return existing.response_body, existing.response_status_code, True
        raise DuplicateIdempotencyKeyError(
            "A request with this idempotency key is currently being processed"
        )

    # Process the payout
    try:
        payout = create_payout(merchant_id, amount_paise, bank_account_id)
        from payouts.serializers import PayoutSerializer

        # Convert UUIDs to strings for JSON storage via DRF's encoder
        response_body = json.loads(json.dumps(PayoutSerializer(payout).data, cls=JSONEncoder))
        response_status = 201

        # Store successful response
        idem_record.response_body = response_body
        idem_record.response_status_code = response_status
        idem_record.is_processing = False
        idem_record.save()

        return response_body, response_status, False

    except Exception as e:
        # Store error response so retries with same key get same error
        error_body = {"error": str(e), "type": type(e).__name__}
        status_code = 400
        if isinstance(e, InsufficientBalanceError):
            status_code = 422
        elif isinstance(e, InvalidBankAccountError):
            status_code = 400

        idem_record.response_body = error_body
        idem_record.response_status_code = status_code
        idem_record.is_processing = False
        idem_record.save()

        raise
