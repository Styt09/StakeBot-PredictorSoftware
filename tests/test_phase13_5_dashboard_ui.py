from __future__ import annotations

from institutional_trading_platform.premium_dashboard import PREMIUM_DASHBOARD_HTML


def test_premium_dashboard_contains_required_safe_sections() -> None:
    required = [
        "LIVE NO-GO",
        "LIVE: NO-GO",
        "go_live_allowed=false",
        "Safety Command Center",
        "Market Watchlist",
        "Safe Signal Panel",
        "Paper Trading Section",
        "Shadow Trading Section",
        "Evidence & 30-Day Tracker Section",
        "Broker Read-Only Section",
        "Audit & Readiness Section",
        "Emergency Safety Section",
        "Virtual only",
        "No broker order placed",
        "Read-only broker access",
    ]
    for expected_text in required:
        assert expected_text in PREMIUM_DASHBOARD_HTML


def test_premium_dashboard_omits_unsafe_controls() -> None:
    forbidden = [
        "Enable " + "Live",
        "Place " + "Real " + "Order",
        "Live " + "Trade " + "Now",
    ]
    for forbidden_text in forbidden:
        assert forbidden_text not in PREMIUM_DASHBOARD_HTML


def test_premium_dashboard_keeps_safe_status_visible() -> None:
    assert PREMIUM_DASHBOARD_HTML.count("go_live_allowed=false") >= 3
    assert "Real Zerodha orders remain blocked" in PREMIUM_DASHBOARD_HTML
    assert "No real-order control is provided" in PREMIUM_DASHBOARD_HTML
