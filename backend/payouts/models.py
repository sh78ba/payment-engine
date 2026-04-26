"""
Models for the Playto Payout Engine.

Key design decisions:
- All amounts stored as BigIntegerField in paise (1 INR = 100 paise). No floats, no decimals.
- Balance is NEVER stored as a field. It is always derived from ledger entries.
- LedgerEntry is the source of truth. Every credit and debit is a row.
- Payout holds the state machine + links to the debit/refund ledger entries.
- IdempotencyKey ensures exactly-once payout creation per merchant.
"""

import uuid
from django.db import models
from django.utils import timezone


class Merchant(models.Model):
    """
    Represents a merchant who can receive payments and request payouts.
    Balance is NOT stored here - it is derived from LedgerEntry rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchants"

    def __str__(self):
        return f"{self.name} ({self.email})"


class BankAccount(models.Model):
    """
    Merchant's Indian bank account for receiving payouts.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="bank_accounts"
    )
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bank_accounts"

    def __str__(self):
        return f"{self.bank_name} - {self.account_number[-4:]}"


class LedgerEntry(models.Model):
    """
    Immutable ledger entry. Source of truth for all money movement.

    Types:
    - CREDIT: Money coming in (customer payment received)
    - DEBIT: Money going out (payout hold placed)
    - REFUND: Money returned (failed payout hold released)

    The merchant's available balance is:
        SUM(amount) WHERE type=CREDIT + SUM(amount) WHERE type=REFUND - SUM(amount) WHERE type=DEBIT

    The held balance is:
        SUM(amount) WHERE type=DEBIT AND related payout is in (PENDING, PROCESSING)
    """

    class EntryType(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"
        REFUND = "REFUND", "Refund"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount_paise = models.BigIntegerField(
        help_text="Amount in paise. Always positive. Direction determined by entry_type."
    )
    description = models.CharField(max_length=500, blank=True, default="")
    # Links a debit/refund to the payout that caused it
    payout = models.ForeignKey(
        "Payout",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "entry_type"]),
            models.Index(fields=["merchant", "created_at"]),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise}p for {self.merchant_id}"


class Payout(models.Model):
    """
    Represents a payout request from a merchant to their bank account.

    State machine:
        PENDING -> PROCESSING -> COMPLETED
        PENDING -> PROCESSING -> FAILED

    Illegal transitions are rejected at the application level via transition_to().
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    # Legal state transitions
    ALLOWED_TRANSITIONS = {
        "PENDING": {"PROCESSING"},
        "PROCESSING": {"COMPLETED", "FAILED"},
        # Terminal states - no transitions out
        "COMPLETED": set(),
        "FAILED": set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="payouts"
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name="payouts"
    )
    amount_paise = models.BigIntegerField(
        help_text="Payout amount in paise."
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    # Retry tracking
    attempt_count = models.IntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payouts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "status"]),
            models.Index(fields=["status", "last_attempted_at"]),
        ]

    def __str__(self):
        return f"Payout {self.id} - {self.amount_paise}p ({self.status})"

    def transition_to(self, new_status):
        """
        Attempt a state transition. Raises ValueError if the transition is illegal.

        This is the ONLY way to change payout status. Direct assignment to
        self.status is not allowed in application code.

        The check here is:
            if new_status not in ALLOWED_TRANSITIONS[current_status]:
                raise ValueError

        This blocks:
        - COMPLETED -> anything
        - FAILED -> anything
        - PROCESSING -> PENDING (backwards)
        - Any skip like PENDING -> COMPLETED
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal state transition: {self.status} -> {new_status}. "
                f"Allowed transitions from {self.status}: {allowed or 'none (terminal state)'}"
            )
        self.status = new_status
        if new_status == self.Status.COMPLETED:
            self.completed_at = timezone.now()
        return self


class IdempotencyKey(models.Model):
    """
    Stores idempotency keys to prevent duplicate payout creation.

    Keys are scoped per merchant and expire after 24 hours.
    The response_data field stores the serialized response from the first
    successful request, so subsequent requests with the same key get
    the exact same response.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="idempotency_keys"
    )
    key = models.CharField(max_length=255)
    # Store the HTTP response for replay
    response_status_code = models.IntegerField(null=True)
    response_body = models.JSONField(null=True)
    # Track if request is still being processed (for concurrent duplicate detection)
    is_processing = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_keys"
        # Unique constraint ensures no duplicate keys per merchant
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "key"],
                name="unique_merchant_idempotency_key",
            )
        ]
        indexes = [
            models.Index(fields=["created_at"]),  # For TTL cleanup
        ]

    def __str__(self):
        return f"Key {self.key} for merchant {self.merchant_id}"

    @property
    def is_expired(self):
        """Check if key is older than 24 hours."""
        from django.conf import settings

        ttl_hours = getattr(settings, "IDEMPOTENCY_KEY_TTL_HOURS", 24)
        return (
            timezone.now() - self.created_at
        ).total_seconds() > ttl_hours * 3600
