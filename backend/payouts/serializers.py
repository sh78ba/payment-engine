from rest_framework import serializers
from payouts.models import Merchant, BankAccount, LedgerEntry, Payout


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_number",
            "ifsc_code",
            "account_holder_name",
            "bank_name",
            "created_at",
        ]


class LedgerEntrySerializer(serializers.ModelSerializer):
    payout_id = serializers.UUIDField(source="payout.id", read_only=True, default=None)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount_paise",
            "description",
            "payout_id",
            "created_at",
        ]


class PayoutSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "merchant_id",
            "bank_account",
            "amount_paise",
            "status",
            "attempt_count",
            "created_at",
            "updated_at",
            "completed_at",
        ]


class PayoutCreateSerializer(serializers.Serializer):
    """
    Validates the payout creation request.
    amount_paise must be a positive integer.
    bank_account_id must be a valid UUID.
    """

    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.UUIDField()

    def validate_amount_paise(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value


class MerchantDashboardSerializer(serializers.ModelSerializer):
    available_balance = serializers.IntegerField(read_only=True)
    held_balance = serializers.IntegerField(read_only=True)
    total_credits = serializers.IntegerField(read_only=True)
    total_debits = serializers.IntegerField(read_only=True)
    bank_accounts = BankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Merchant
        fields = [
            "id",
            "name",
            "email",
            "available_balance",
            "held_balance",
            "total_credits",
            "total_debits",
            "bank_accounts",
            "created_at",
        ]
