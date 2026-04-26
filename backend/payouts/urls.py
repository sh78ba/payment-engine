from django.urls import path
from payouts import views

urlpatterns = [
    # Merchant endpoints
    path("merchants/", views.merchant_list, name="merchant-list"),
    path(
        "merchants/<uuid:merchant_id>/dashboard/",
        views.merchant_dashboard,
        name="merchant-dashboard",
    ),
    path(
        "merchants/<uuid:merchant_id>/ledger/",
        views.merchant_ledger,
        name="merchant-ledger",
    ),
    # Payout endpoints - POST and GET on the same path
    path(
        "merchants/<uuid:merchant_id>/payouts/",
        views.create_payout_view,
        name="payout-create",
    ),
    path(
        "merchants/<uuid:merchant_id>/payouts/list/",
        views.payout_list,
        name="payout-list",
    ),
    path(
        "merchants/<uuid:merchant_id>/payouts/<uuid:payout_id>/",
        views.payout_detail,
        name="payout-detail",
    ),
]
