# EXPLAINER.md

## 1. The Ledger

### Balance Calculation Query

The balance is **never stored as a field**. It is always derived from ledger entries via database-level aggregation.

```python
# backend/payouts/services/ledger.py

def get_merchant_balance(merchant_id):
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
```

This translates to:

```sql
SELECT COALESCE(SUM(
    CASE
        WHEN entry_type IN ('CREDIT', 'REFUND') THEN amount_paise
        WHEN entry_type = 'DEBIT' THEN amount_paise * -1
        ELSE 0
    END
), 0) AS total
FROM ledger_entries
WHERE merchant_id = %s;
```

### Why this model?

I chose **three entry types** (CREDIT, DEBIT, REFUND) instead of just positive/negative amounts because:

1. **Auditability**: Every money movement has a clear type. When a payout fails, you see a DEBIT when the hold was placed and a REFUND when funds returned — not just two numbers with opposite signs.

2. **Query clarity**: "Show me all refunds" is `WHERE entry_type = 'REFUND'`, not `WHERE amount > 0 AND payout_id IS NOT NULL AND payout__status = 'FAILED'`.

3. **Invariant checking**: The available balance formula is `SUM(CREDITS) + SUM(REFUNDS) - SUM(DEBITS)`. This is verifiable and easy to audit. The held balance is `SUM(DEBITS WHERE payout is PENDING or PROCESSING)`.

4. **Immutability**: Ledger entries are append-only. We never update or delete them. A "reversal" is a new REFUND entry. This is how real accounting works — you don't erase entries, you counter-post.

I deliberately chose **not** to cache the balance on the Merchant model. Cached balances drift. In a money system, "the balance is whatever the ledger says" is the only safe invariant. The cost is an aggregate query per balance check, but with proper indexes on `(merchant_id, entry_type)`, this is fast even at scale.

---

## 2. The Lock

### The Code

```python
# backend/payouts/services/payout.py - create_payout()

with transaction.atomic():
    # STEP 1: Acquire exclusive lock on the merchant row.
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    # STEP 2: Validate bank account belongs to this merchant
    bank_account = BankAccount.objects.get(id=bank_account_id, merchant=merchant)

    # STEP 3: Compute available balance INSIDE the transaction
    available = get_available_balance(merchant_id)

    if available < amount_paise:
        raise InsufficientBalanceError(...)

    # STEP 4: Create the payout
    payout = Payout.objects.create(...)

    # STEP 5: Create the debit ledger entry
    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.DEBIT,
        amount_paise=amount_paise,
        ...
    )
```

### What database primitive it relies on

**`SELECT ... FOR UPDATE`** — this is PostgreSQL's row-level exclusive lock.

When transaction A executes `SELECT * FROM merchants WHERE id = X FOR UPDATE`, it acquires an exclusive lock on that row. If transaction B tries the same `SELECT FOR UPDATE` on the same row, it **blocks** (waits) until transaction A commits or rolls back.

Here's the timeline for the two-concurrent-60-rupee-requests scenario:

```
Thread A                          Thread B
─────────                         ─────────
BEGIN                              BEGIN
SELECT FOR UPDATE (merchant X)     SELECT FOR UPDATE (merchant X)
  → acquires lock                    → BLOCKS (waiting for A's lock)
get_available_balance() → 10000
10000 >= 6000 → OK
CREATE payout (6000)
CREATE debit entry (6000)
COMMIT → releases lock
                                     → lock acquired
                                   get_available_balance() → 4000
                                   4000 < 6000 → REJECT
                                   ROLLBACK
```

The key insight: the balance check happens **inside** the locked transaction. Thread B doesn't read the balance until Thread A has committed its debit. This is why Python-level locks (like `threading.Lock()`) are wrong here — they don't protect against database-level read-then-write races across multiple Django processes or Celery workers.

I chose to lock on the **Merchant row** rather than individual ledger entries because:
- It's simple and correct — one lock per merchant serializes all that merchant's payouts
- The lock duration is short (one DB query + two inserts)
- It doesn't block payouts for other merchants

Alternative: `select_for_update()` on the ledger entries themselves with `SERIALIZABLE` isolation. But that's overkill for this use case and brings deadlock risks.

---

## 3. The Idempotency

### How the system knows it has seen a key before

The `IdempotencyKey` model with a **unique constraint** on `(merchant_id, key)`:

```python
class IdempotencyKey(models.Model):
    merchant = models.ForeignKey(Merchant, ...)
    key = models.CharField(max_length=255)
    response_status_code = models.IntegerField(null=True)
    response_body = models.JSONField(null=True)
    is_processing = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "key"],
                name="unique_merchant_idempotency_key",
            )
        ]
```

The flow in `handle_idempotent_payout()`:

1. **Check** if the key exists and isn't expired (> 24 hours old)
   - If exists and `is_processing=False`: return the stored `response_body` and `response_status_code`. This is a **replay**.
   - If exists and `is_processing=True`: the first request is still running. Return 409 Conflict.
2. **If not found**: INSERT a new row with `is_processing=True`, then process the payout.
3. **After processing** (success or failure): update the row with the response and set `is_processing=False`.

### What happens if the first request is in flight when the second arrives

Two scenarios:

**Scenario A: Second request arrives after first INSERT but before first COMMIT**

The second request tries `INSERT INTO idempotency_keys (merchant_id, key, ...)`. The unique constraint on `(merchant_id, key)` causes an `IntegrityError`. We catch it:

```python
except IntegrityError:
    existing = IdempotencyKey.objects.filter(
        merchant_id=merchant_id, key=idempotency_key, ...
    ).first()
    if existing and not existing.is_processing:
        return existing.response_body, existing.response_status_code, True
    raise DuplicateIdempotencyKeyError(...)
```

If the first request has finished (`is_processing=False`), we replay the response. If it's still processing, we return 409.

**Scenario B: Second request arrives after first's lookup but before first's INSERT**

Both do the initial `SELECT` and find nothing. Both try `INSERT`. The database unique constraint guarantees that only one INSERT succeeds. The other gets `IntegrityError` and falls into the catch block above.

The key principle: we don't rely on the application-level "check then insert" being atomic. We rely on the **database unique constraint** as the ultimate arbiter.

---

## 4. The State Machine

### Where failed-to-completed is blocked

In the `Payout.transition_to()` method:

```python
# backend/payouts/models.py - Payout class

ALLOWED_TRANSITIONS = {
    "PENDING": {"PROCESSING"},
    "PROCESSING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),    # Terminal — no transitions out
    "FAILED": set(),       # Terminal — no transitions out
}

def transition_to(self, new_status):
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
```

`FAILED` maps to an empty set `set()`. So `transition_to("COMPLETED")` when current status is `FAILED` hits:
- `allowed = set()` (empty)
- `"COMPLETED" not in set()` → `True`
- → `ValueError("Illegal state transition: FAILED -> COMPLETED...")`

The same applies to `COMPLETED -> PENDING`, `COMPLETED -> FAILED`, or any backwards movement. Both terminal states have empty allowed sets.

This method is the **only** way status changes happen in application code. The Celery tasks (`_complete_payout`, `_fail_payout`, `process_single_payout`) all call `payout.transition_to(new_status)` rather than setting `payout.status` directly.

The one exception: the retry logic in `retry_stuck_payouts()` bypasses the state machine for `PROCESSING -> PENDING` resets. This is intentional and documented in the code comment — retries need to move backwards, but only from `PROCESSING`, and only when the payout has timed out.

---

## 5. The AI Audit

### The Bug: Double-counting held balance in available balance calculation

AI generated the available balance calculation as `total_balance - held_balance`. This looks correct at first glance but contains a subtle double-counting bug that only surfaces when payouts are in PENDING or PROCESSING state.

**What AI generated (wrong):**

```python
def get_available_balance(merchant_id):
    """Available balance = total balance - held balance"""
    total = get_merchant_balance(merchant_id)  # Credits + Refunds - ALL Debits
    held = get_held_balance(merchant_id)       # Debits for PENDING/PROCESSING payouts
    return total - held
```

**What's wrong:** `get_merchant_balance()` already subtracts ALL debits from the total, including debits for pending/processing payouts. Then `get_available_balance()` subtracts `held_balance` (which is the sum of those same pending/processing debits) again. The pending/processing debits are subtracted **twice**.

Walk through with numbers:
1. Merchant gets ₹500 credit (50000 paise) → total = 50000
2. Merchant requests ₹100 payout → DEBIT of 10000 created
3. `get_merchant_balance()` = 50000 (credits) - 10000 (debits) = **40000**
4. `get_held_balance()` = 10000 (PENDING payout debit)
5. AI code: available = 40000 - 10000 = **30000** ← WRONG, should be **40000**

The merchant should have ₹400 available (total ₹500 minus ₹100 being held). But the AI code says ₹300. It "lost" ₹100 by counting the hold twice.

This bug was invisible in unit tests with only credits — it only appeared when I wrote the idempotency test that creates a payout and then checks the available balance.

**What I replaced it with:**

```python
def get_available_balance(merchant_id):
    """
    Available = get_merchant_balance() directly.
    
    Total balance already accounts for all debits (including holds).
    A DEBIT entry is created when a payout is created (holds funds).
    A REFUND entry is created when a payout fails (returns funds).
    So total = credits + refunds - all debits = what's truly withdrawable.
    """
    return get_merchant_balance(merchant_id)
```

The held balance is now only used for *display purposes* on the dashboard — showing the merchant how much is tied up in in-flight payouts. It doesn't factor into the withdrawal eligibility check because the debit ledger entry already handles that.

**Why this matters:** The double-counting means merchants would be blocked from withdrawing money they legitimately have. In a payout system, falsely rejecting valid withdrawal requests is almost as bad as allowing overdrafts — merchants lose trust and revenue. The concurrency test (`test_concurrent_payouts_both_within_balance`) caught this: two ₹40 payouts on a ₹100 balance should both succeed, but the buggy code rejected the second one because it calculated available as ₹20 instead of ₹60.

### Lesson

AI confidently generates financial formulas that "look right" — `available = total - held` reads like a textbook definition. But when the total already incorporates the holds through the debit entries, subtracting them again is wrong. The only way to catch this is to trace through actual numbers. Every time AI generates a balance calculation, I now manually walk through a payout lifecycle (create, hold, fail, refund) with concrete numbers before trusting it.
