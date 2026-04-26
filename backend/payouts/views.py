"""
API views for the Playto Payout Engine.

Authentication is simplified - merchant_id is passed as a URL parameter or header.
In production, this would be replaced with proper auth (JWT, API keys, etc.).
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from payouts.models import Merchant, LedgerEntry, Payout
from payouts.serializers import (
    MerchantDashboardSerializer,
    LedgerEntrySerializer,
    PayoutSerializer,
    PayoutCreateSerializer,
)
from payouts.services import (
    get_available_balance,
    get_held_balance,
    get_total_credits,
    get_total_debits,
    handle_idempotent_payout,
    create_payout,
    InsufficientBalanceError,
    InvalidBankAccountError,
    DuplicateIdempotencyKeyError,
)


@api_view(["GET"])
def merchant_list(request):
    """List all merchants with basic info."""
    merchants = Merchant.objects.all()
    data = []
    for m in merchants:
        data.append({
            "id": str(m.id),
            "name": m.name,
            "email": m.email,
            "available_balance": get_available_balance(m.id),
            "held_balance": get_held_balance(m.id),
        })
    return Response(data)


@api_view(["GET"])
def merchant_dashboard(request, merchant_id):
    """
    GET /api/v1/merchants/<merchant_id>/dashboard/

    Returns the full merchant dashboard data:
    - Available balance
    - Held balance
    - Total credits and debits
    - Bank accounts
    """
    try:
        merchant = Merchant.objects.get(id=merchant_id)
    except Merchant.DoesNotExist:
        return Response(
            {"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND
        )

    data = MerchantDashboardSerializer(merchant).data
    data["available_balance"] = get_available_balance(merchant_id)
    data["held_balance"] = get_held_balance(merchant_id)
    data["total_credits"] = get_total_credits(merchant_id)
    data["total_debits"] = get_total_debits(merchant_id)

    return Response(data)


@api_view(["GET"])
def merchant_ledger(request, merchant_id):
    """
    GET /api/v1/merchants/<merchant_id>/ledger/

    Returns recent ledger entries for the merchant.
    """
    try:
        Merchant.objects.get(id=merchant_id)
    except Merchant.DoesNotExist:
        return Response(
            {"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND
        )

    entries = LedgerEntry.objects.filter(merchant_id=merchant_id).order_by(
        "-created_at"
    )[:50]
    serializer = LedgerEntrySerializer(entries, many=True)
    return Response(serializer.data)


@api_view(["POST"])
def create_payout_view(request, merchant_id):
    """
    POST /api/v1/merchants/<merchant_id>/payouts/

    Headers:
        Idempotency-Key: <uuid> (required)

    Body:
        {
            "amount_paise": 500000,
            "bank_account_id": "<uuid>"
        }

    Creates a payout in PENDING state and holds the funds.
    Uses SELECT FOR UPDATE to prevent concurrent overdraw.
    Respects idempotency key for exactly-once semantics.
    """
    # Validate merchant exists
    try:
        Merchant.objects.get(id=merchant_id)
    except Merchant.DoesNotExist:
        return Response(
            {"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Validate request body
    serializer = PayoutCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    amount_paise = serializer.validated_data["amount_paise"]
    bank_account_id = serializer.validated_data["bank_account_id"]

    # Get idempotency key from header
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response(
            {"error": "Idempotency-Key header is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Handle with idempotency
    try:
        response_body, response_status, is_replay = handle_idempotent_payout(
            merchant_id=merchant_id,
            amount_paise=amount_paise,
            bank_account_id=bank_account_id,
            idempotency_key=idempotency_key,
        )

        response = Response(response_body, status=response_status)
        if is_replay:
            response["X-Idempotency-Replay"] = "true"
        return response

    except InsufficientBalanceError as e:
        return Response(
            {"error": str(e), "type": "insufficient_balance"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except InvalidBankAccountError as e:
        return Response(
            {"error": str(e), "type": "invalid_bank_account"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except DuplicateIdempotencyKeyError as e:
        return Response(
            {"error": str(e), "type": "duplicate_request"},
            status=status.HTTP_409_CONFLICT,
        )


@api_view(["GET"])
def payout_list(request, merchant_id):
    """
    GET /api/v1/merchants/<merchant_id>/payouts/

    Returns all payouts for the merchant, ordered by creation date.
    """
    try:
        Merchant.objects.get(id=merchant_id)
    except Merchant.DoesNotExist:
        return Response(
            {"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND
        )

    payouts = Payout.objects.filter(merchant_id=merchant_id).select_related(
        "bank_account"
    )
    serializer = PayoutSerializer(payouts, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def payout_detail(request, merchant_id, payout_id):
    """
    GET /api/v1/merchants/<merchant_id>/payouts/<payout_id>/

    Returns a single payout's details.
    """
    try:
        payout = Payout.objects.select_related("bank_account").get(
            id=payout_id, merchant_id=merchant_id
        )
    except Payout.DoesNotExist:
        return Response(
            {"error": "Payout not found"}, status=status.HTTP_404_NOT_FOUND
        )

    serializer = PayoutSerializer(payout)
    return Response(serializer.data)
