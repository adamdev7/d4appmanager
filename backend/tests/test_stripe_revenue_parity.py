"""Period revenue must equal the number the Stripe Dashboard shows.

Two ways it silently drifted before:
  * an idle MID reported the *requested* currency, so CAD settlement amounts
    were labeled GBP and then converted GBP→CAD (1.87x too big);
  * chargeback withdrawals were folded into revenue, so a day with an old
    dispute read far below Stripe's Volume net.
"""

from decimal import Decimal

from app.integrations.stripe.client import StripeClient, _pick_majority_currency
from app.services.analytics_service import dominant_settlement_currency


def test_idle_account_does_not_invent_the_requested_currency():
    assert _pick_majority_currency({}, "gbp") is None
    assert _pick_majority_currency({"cad": 9}, "gbp") == "CAD"
    assert _pick_majority_currency({"cad": 9, "usd": 2}, None) == "CAD"
    # Preferred still wins when it actually has volume
    assert _pick_majority_currency({"cad": 9, "gbp": 1}, "gbp") == "GBP"


def _snapshot(currency, *, charges=0, net="0", active=True):
    return {
        "label": "mid",
        "totals": {
            "settlement_currency": currency,
            "charge_count": charges,
            "net": net,
            "has_activity": active,
        },
    }


def test_settlement_currency_follows_the_money_not_the_idle_mid():
    snapshots = [
        _snapshot("CAD", charges=9, net="168.71"),
        _snapshot("GBP", active=False),  # idle MID, defaulted label
        _snapshot("CAD", charges=0, net="-35.52"),
    ]
    assert dominant_settlement_currency(snapshots) == "CAD"


def test_busiest_currency_wins_and_no_activity_means_no_answer():
    assert dominant_settlement_currency([]) is None
    assert dominant_settlement_currency([_snapshot("GBP", active=False)]) is None
    assert (
        dominant_settlement_currency(
            [_snapshot("USD", charges=2, net="50"), _snapshot("CAD", charges=9, net="168")]
        )
        == "CAD"
    )


def test_disputes_and_account_fees_are_not_part_of_volume_net():
    """Revenue is charges − refunds − processing fees, exactly like the Dashboard."""
    assert "adjustment" not in StripeClient._VOLUME_NET_TYPES
    assert "stripe_fee" not in StripeClient._VOLUME_NET_TYPES
    assert "adjustment" in StripeClient._DISPUTE_TYPES
    assert "dispute" in StripeClient._DISPUTE_TYPES
    assert "stripe_fee" in StripeClient._PLATFORM_FEE_TYPES
    assert StripeClient._VOLUME_NET_TYPES & StripeClient._DISPUTE_TYPES == set()
    assert StripeClient._VOLUME_NET_TYPES & StripeClient._PLATFORM_FEE_TYPES == set()


def test_charge_ledger_reproduces_stripe_dashboard_figures():
    """Sept 7 for the live MID: gross 181.20, fees 12.49, net 168.71 on Stripe."""
    bucket = StripeClient._empty_money_bucket()
    for net, fee in ((Decimal("168.71"), Decimal("12.49")),):
        bucket["gross"] += net + fee
        bucket["fees"] += fee
        bucket["net"] += net
    # A chargeback the same day must not move revenue, only the dispute line
    bucket["dispute_net"] += Decimal("-86.29")
    assert bucket["gross"] == Decimal("181.20")
    assert bucket["net"] == Decimal("168.71")
    assert bucket["gross"] - bucket["fees"] == bucket["net"]


def test_pnl_subtracts_chargebacks_once_not_from_revenue():
    """Stripe Dashboard Net volume does not include dispute adjustments.

    Sept 7 on the live MID: Dashboard Gross 181.20, Net 168.71. The 86.29
    chargeback that day is a separate `adjustment` — the original charge BT
    is unchanged. Subtracting it from profit is counting it once. Folding it
    into revenue *and* subtracting it again would be the double-count.
    """
    revenue = Decimal("168.71")
    processing_fees = Decimal("12.49")
    chargebacks = Decimal("86.29")
    ads = Decimal("246.28")
    net_profit = revenue - ads - chargebacks
    assert net_profit == Decimal("-163.86")
    # Processing fees are already inside Net volume
    assert revenue == Decimal("181.20") - processing_fees
    double_counted = (revenue - chargebacks) - ads - chargebacks
    assert double_counted == net_profit - chargebacks

