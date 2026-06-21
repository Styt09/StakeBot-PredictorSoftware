from __future__ import annotations

from institutional_trading_platform.advanced_research_pipeline import (
    DATA_UNAVAILABLE,
    GO_LIVE_ALLOWED,
    AdvancedResearchPipeline,
    ResearchAdapterType,
    research_adapter_catalog,
)


def _trend_rows(direction: str = "up", n: int = 80):
    rows = []
    price = 100.0
    for i in range(n):
        price += 0.55 if direction == "up" else -0.55
        rows.append(
            {
                "timestamp": f"2026-01-01T09:{i:02d}:00+05:30",
                "open": price - 0.2,
                "high": price + 0.9,
                "low": price - 0.45,
                "close": price,
                "volume": 10000 + i * 150,
            }
        )
    return rows


def _flat_rows(n: int = 20):
    return [
        {
            "timestamp": f"2026-01-01T09:{i:02d}:00+05:30",
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "volume": 1000,
        }
        for i in range(n)
    ]


def test_catalog_contains_all_five_research_options():
    adapters = {row["adapter"] for row in research_adapter_catalog()}
    assert adapters == {item.value for item in ResearchAdapterType}
    assert all(row["go_live_allowed"] is False for row in research_adapter_catalog())


def test_insufficient_candles_returns_data_unavailable():
    signal = AdvancedResearchPipeline().evaluate_signal("RELIANCE", _flat_rows(10))
    assert signal["decision"] == DATA_UNAVAILABLE
    assert signal["go_live_allowed"] is GO_LIVE_ALLOWED


def test_bullish_research_signal_uses_all_adapters_and_stays_safe():
    signal = AdvancedResearchPipeline().evaluate_signal("RELIANCE", _trend_rows("up", 80))
    assert len(signal["adapter_scores"]) == 5
    assert signal["go_live_allowed"] is False
    assert signal["validation_status"] == "VALIDATED"
    assert signal["decision"] in {"BUY", "NO_TRADE"}
    if signal["decision"] == "BUY":
        assert signal["risk_reward"] == 2.0
        assert signal["entry"] != DATA_UNAVAILABLE


def test_bearish_research_signal_uses_all_adapters_and_stays_safe():
    signal = AdvancedResearchPipeline().evaluate_signal("RELIANCE", _trend_rows("down", 80))
    assert len(signal["adapter_scores"]) == 5
    assert signal["go_live_allowed"] is False
    assert signal["validation_status"] == "VALIDATED"
    assert signal["decision"] in {"SELL", "NO_TRADE"}


def test_walk_forward_splits_are_safe():
    splits = AdvancedResearchPipeline().walk_forward_splits(_trend_rows("up", 180), train_size=80, test_size=20, step=20)
    assert splits
    assert all(row["go_live_allowed"] is False for row in splits)
    assert splits[0]["train_start"] == 0
    assert splits[0]["test_start"] == 80


def test_backtest_does_not_fabricate_accuracy_before_enough_outcomes():
    result = AdvancedResearchPipeline().backtest("RELIANCE", _trend_rows("up", 60), lookback=35, forward_bars=5)
    summary = result["summary"]
    assert summary["go_live_allowed"] is False
    assert summary["adapter_family_count"] == 5
    if summary["completed_outcomes"] < 30:
        assert summary["proven_accuracy"] == DATA_UNAVAILABLE
        assert summary["reason"] == "INSUFFICIENT_COMPLETED_BACKTEST_OUTCOMES"


def test_backtest_can_calculate_accuracy_after_enough_completed_outcomes():
    result = AdvancedResearchPipeline().backtest("RELIANCE", _trend_rows("up", 140), lookback=35, forward_bars=5)
    summary = result["summary"]
    assert summary["go_live_allowed"] is False
    if summary["completed_outcomes"] >= 30:
        assert isinstance(summary["proven_accuracy"], float)
        assert 0 <= summary["proven_accuracy"] <= 100
    else:
        assert summary["proven_accuracy"] == DATA_UNAVAILABLE


def test_export_payload_has_no_secret_like_fields():
    result = AdvancedResearchPipeline().backtest("RELIANCE", _trend_rows("up", 90), lookback=35, forward_bars=5)
    text = str(result).lower()
    assert "api_secret" not in text
    assert "access_token" not in text
    assert "request_token" not in text
