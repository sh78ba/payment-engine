from django.contrib import admin
from payouts.models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    search_fields = ("name", "email")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("merchant", "bank_name", "account_number", "ifsc_code")
    list_filter = ("bank_name",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("merchant", "entry_type", "amount_paise", "created_at")
    list_filter = ("entry_type",)
    ordering = ("-created_at",)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "merchant",
        "amount_paise",
        "status",
        "attempt_count",
        "created_at",
    )
    list_filter = ("status",)
    ordering = ("-created_at",)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("merchant", "key", "is_processing", "created_at")
    list_filter = ("is_processing",)
