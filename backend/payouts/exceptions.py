"""
Custom exception handler for DRF.
Maps our domain exceptions to proper HTTP responses.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """Extend DRF's default exception handler with our domain exceptions."""
    response = exception_handler(exc, context)

    if response is not None:
        return response

    # Handle our domain exceptions
    from payouts.services.payout import (
        InsufficientBalanceError,
        InvalidBankAccountError,
        DuplicateIdempotencyKeyError,
    )

    if isinstance(exc, InsufficientBalanceError):
        return Response(
            {"error": str(exc), "type": "insufficient_balance"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if isinstance(exc, InvalidBankAccountError):
        return Response(
            {"error": str(exc), "type": "invalid_bank_account"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, DuplicateIdempotencyKeyError):
        return Response(
            {"error": str(exc), "type": "duplicate_request"},
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, ValueError):
        return Response(
            {"error": str(exc), "type": "validation_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Let Django handle anything else
    return None
