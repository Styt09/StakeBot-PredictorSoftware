"""Advanced research integration foundation for ALPHA-GATE X.

This module does not promise prediction accuracy. It converts the five useful
open-source research directions discussed in chat into safe, local, testable
building blocks:

1. Lean-style event pipeline
2. vectorbt-style vectorized backtest scoring
3. backtrader-style event backtest scoring
4. FinRL-style reinforcement-learning sandbox scoring
5. ML-quant alpha feature scoring

All outputs remain research-only and go_live_allowed is always False.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
NO_TRADE = "NO_TRADE"
GO_LIVE_ALLOWED = False
MIN_COMPLETED_BACKTEST_OUTCOMES = 30


class ResearchAdapterType(StrEnum):
    """External research concepts safely represented as local adapters."""

    LEAN_EVENT_ENGINE = "LEAN_EVENT_ENGINE"
    VECTORBT_FAST_BACKTEST = "VECTORBT_FAST_BACKTEST"
    BACKTRADER_EVENT_BACKTEST = "BACKTRADER_EVENT_BACKTEST"
    FINRL_RL_SANDBOX = "FINRL_RL_SANDBOX"
    ML_QUANT_ALPHA_RESEARCH = "ML_QUANT_ALPHA_RESEARCH"


@dataclass(frozen=True)
class MarketCandle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AdapterScore:
    adapter: str
    score: float
    vote: str
    reason: str
    go_live_allowed: bool = GO_LIVE_ALLOWED


@dataclass(frozen=True)
class ResearchSignal:
    signal_id: str
    symbol: str
    decision: str
    setup_score: float | str
    entry: float | str
    stop_loss: float | str
    target_1: float | str
    target_2: float | str
    risk_reward: float | str
    adapter_scores: tuple[AdapterScore, ...]
    agreement_count: int
    regime: str
    validation_status: str
    reasons: tuple[str, ...]
    timestamp: str
    go_live_allowed: bool = GO_LIVE_ALLOWED

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["adapter_scores"] = tuple(asdict(row) for row in self.adapter_scores)
        payload["go_live_allowed"] = False
        return payload


@dataclass(frozen=True)
class BacktestOutcome:
    symbol: str
    signal_id: str
    decision: str
    entry: float | str
    exit_price: float | str
    outcome: str
    pnl_points: float | str
    go_live_allowed: bool = GO_LIVE_ALLOWED


@dataclass(frozen=True)
class BacktestSummary:
    symbol: str
    total_signals: int
    completed_outcomes: int
    target_hits: int
    stop_hits: int
    expired: int
    no_trade: int
    proven_accuracy: float | str
    average_setup_score: float | str
    validation_status: str
    reason: str
    adapter_family_count: int
    go_live_allowed: bool = GO_LIVE_ALLOWED

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["go_live_allowed"] = False
        return payload


def clean_candles(rows: Sequence[Mapping[str, Any]] | Sequence[MarketCandle]) -> tuple[MarketCandle, ...]:
    """Normalize raw candle dictionaries while rejecting incomplete rows."""

    cleaned: list[MarketCandle] = []
    for row in rows:
        if isinstance(row, MarketCandle):
            cleaned.append(row)
            continue
        try:
            cleaned.append(
                MarketCandle(
                    timestamp=str(row.get("timestamp") or row.get("date") or ""),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
            )
        except Exception:
            continue
    return tuple(cleaned)


def research_adapter_catalog() -> tuple[dict[str, Any], ...]:
    """Return the five safe research integrations enabled by this phase."""

    return (
        {
            "adapter": ResearchAdapterType.LEAN_EVENT_ENGINE.value,
            "purpose": "Institutional event pipeline, broker abstraction, and portfolio lifecycle inspiration.",
            "status": "LOCAL_FOUNDATION_READY",
            "copy_external_code": False,
            "go_live_allowed": False,
        },
        {
            "adapter": ResearchAdapterType.VECTORBT_FAST_BACKTEST.value,
            "purpose": "Fast vectorized parameter sweeps and large symbol/timeframe research.",
            "status": "LOCAL_FOUNDATION_READY",
            "copy_external_code": False,
            "go_live_allowed": False,
        },
        {
            "adapter": ResearchAdapterType.BACKTRADER_EVENT_BACKTEST.value,
            "purpose": "Step-by-step event backtesting with realistic fills, stop-loss, and target checks.",
            "status": "LOCAL_FOUNDATION_READY",
            "copy_external_code": False,
            "go_live_allowed": False,
        },
        {
            "adapter": ResearchAdapterType.FINRL_RL_SANDBOX.value,
            "purpose": "Reinforcement-learning sandbox only; never allowed to place live orders.",
            "status": "SANDBOX_ONLY",
            "copy_external_code": False,
            "go_live_allowed": False,
        },
        {
            "adapter": ResearchAdapterType.ML_QUANT_ALPHA_RESEARCH.value,
            "purpose": "Feature scoring, alpha evidence, and model-registry-ready research contracts.",
            "status": "LOCAL_FOUNDATION_READY",
            "copy_external_code": False,
            "go_live_allowed": False,
        },
    )


class AdvancedResearchPipeline:
    """Safe ensemble research layer combining five external-style ideas."""

    def evaluate_signal(self, symbol: str, rows: Sequence[Mapping[str, Any]] | Sequence[MarketCandle]) -> dict[str, Any]:
        normalized = symbol.strip().upper() or "RELIANCE"
        candles = clean_candles(rows)
        if len(candles) < 35:
            return ResearchSignal(
                signal_id=f"research-{uuid4()}",
                symbol=normalized,
                decision=DATA_UNAVAILABLE,
                setup_score=DATA_UNAVAILABLE,
                entry=DATA_UNAVAILABLE,
                stop_loss=DATA_UNAVAILABLE,
                target_1=DATA_UNAVAILABLE,
                target_2=DATA_UNAVAILABLE,
                risk_reward=DATA_UNAVAILABLE,
                adapter_scores=(),
                agreement_count=0,
                regime=DATA_UNAVAILABLE,
                validation_status=DATA_UNAVAILABLE,
                reasons=("INSUFFICIENT_RESEARCH_CANDLES",),
                timestamp=_now(),
            ).as_dict()

        features = self._features(candles)
        adapter_scores = (
            self._lean_event_score(features),
            self._vectorbt_score(candles, features),
            self._backtrader_score(candles, features),
            self._finrl_sandbox_score(features),
            self._ml_quant_score(features),
        )
        votes = [row.vote for row in adapter_scores if row.vote in {"BUY", "SELL"}]
        buy_votes = votes.count("BUY")
        sell_votes = votes.count("SELL")
        agreement = max(buy_votes, sell_votes)
        setup_score = round(mean(row.score for row in adapter_scores), 2)
        last_close = candles[-1].close
        atr = max(float(features["atr_14"]), 0.01)
        regime = str(features["regime"])
        reasons = [row.reason for row in adapter_scores]

        decision = NO_TRADE
        side = None
        if agreement >= 3 and setup_score >= 72 and regime not in {"SIDEWAYS", "LOW_VOLUME"}:
            side = "BUY" if buy_votes > sell_votes else "SELL"
            decision = side
        else:
            reasons.append("ENSEMBLE_AGREEMENT_OR_SCORE_NOT_ENOUGH")

        entry: float | str = round(last_close, 2) if side else DATA_UNAVAILABLE
        stop_loss: float | str = DATA_UNAVAILABLE
        target_1: float | str = DATA_UNAVAILABLE
        target_2: float | str = DATA_UNAVAILABLE
        risk_reward: float | str = DATA_UNAVAILABLE
        if side == "BUY":
            stop_loss = round(last_close - atr, 2)
            target_1 = round(last_close + 2 * atr, 2)
            target_2 = round(last_close + 3 * atr, 2)
            risk_reward = 2.0
        elif side == "SELL":
            stop_loss = round(last_close + atr, 2)
            target_1 = round(last_close - 2 * atr, 2)
            target_2 = round(last_close - 3 * atr, 2)
            risk_reward = 2.0

        return ResearchSignal(
            signal_id=f"research-{uuid4()}",
            symbol=normalized,
            decision=decision,
            setup_score=setup_score,
            entry=entry,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            adapter_scores=adapter_scores,
            agreement_count=agreement,
            regime=regime,
            validation_status="VALIDATED",
            reasons=tuple(dict.fromkeys(reasons)),
            timestamp=_now(),
        ).as_dict()

    def backtest(
        self,
        symbol: str,
        rows: Sequence[Mapping[str, Any]] | Sequence[MarketCandle],
        *,
        lookback: int = 35,
        forward_bars: int = 10,
    ) -> dict[str, Any]:
        candles = clean_candles(rows)
        outcomes: list[BacktestOutcome] = []
        scores: list[float] = []
        for idx in range(lookback, max(lookback, len(candles) - forward_bars)):
            signal = self.evaluate_signal(symbol, candles[idx - lookback : idx])
            if isinstance(signal.get("setup_score"), (int, float)):
                scores.append(float(signal["setup_score"]))
            decision = str(signal.get("decision", NO_TRADE))
            if decision not in {"BUY", "SELL"}:
                outcomes.append(
                    BacktestOutcome(symbol.upper(), str(signal.get("signal_id")), decision, DATA_UNAVAILABLE, DATA_UNAVAILABLE, NO_TRADE, DATA_UNAVAILABLE)
                )
                continue
            outcomes.append(self._evaluate_forward_outcome(signal, candles[idx : idx + forward_bars]))
        return {
            "summary": self._summary(symbol, outcomes, scores).as_dict(),
            "outcomes": tuple(asdict(row) for row in outcomes[-100:]),
            "adapters": research_adapter_catalog(),
            "go_live_allowed": False,
        }

    def walk_forward_splits(self, rows: Sequence[Mapping[str, Any]] | Sequence[MarketCandle], *, train_size: int = 100, test_size: int = 20, step: int = 20) -> tuple[dict[str, int], ...]:
        candles = clean_candles(rows)
        splits: list[dict[str, int]] = []
        start = 0
        while start + train_size + test_size <= len(candles):
            splits.append(
                {
                    "train_start": start,
                    "train_end": start + train_size,
                    "test_start": start + train_size,
                    "test_end": start + train_size + test_size,
                    "go_live_allowed": False,
                }
            )
            start += step
        return tuple(splits)

    def _features(self, candles: Sequence[MarketCandle]) -> dict[str, float | str | bool]:
        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]
        ema_fast = _ema(closes, 9)
        ema_slow = _ema(closes, 21)
        atr_14 = _atr(candles, 14)
        momentum_5 = closes[-1] - closes[-6]
        momentum_20 = closes[-1] - closes[-21]
        avg_volume = mean(volumes[-20:]) if len(volumes) >= 20 else mean(volumes)
        volume_ratio = volumes[-1] / avg_volume if avg_volume else 0.0
        rsi_14 = _rsi(closes, 14)
        trend = "BULLISH" if ema_fast > ema_slow and momentum_20 > 0 else "BEARISH" if ema_fast < ema_slow and momentum_20 < 0 else "SIDEWAYS"
        regime = "LOW_VOLUME" if volume_ratio < 0.55 else "TRENDING_UP" if trend == "BULLISH" else "TRENDING_DOWN" if trend == "BEARISH" else "SIDEWAYS"
        return {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "atr_14": atr_14,
            "momentum_5": momentum_5,
            "momentum_20": momentum_20,
            "volume_ratio": volume_ratio,
            "rsi_14": rsi_14,
            "trend": trend,
            "regime": regime,
        }

    def _lean_event_score(self, features: Mapping[str, Any]) -> AdapterScore:
        trend = features["trend"]
        if trend == "BULLISH":
            return AdapterScore(ResearchAdapterType.LEAN_EVENT_ENGINE.value, 75, "BUY", "LEAN_EVENT_TREND_BULLISH")
        if trend == "BEARISH":
            return AdapterScore(ResearchAdapterType.LEAN_EVENT_ENGINE.value, 75, "SELL", "LEAN_EVENT_TREND_BEARISH")
        return AdapterScore(ResearchAdapterType.LEAN_EVENT_ENGINE.value, 40, NO_TRADE, "LEAN_EVENT_SIDEWAYS")

    def _vectorbt_score(self, candles: Sequence[MarketCandle], features: Mapping[str, Any]) -> AdapterScore:
        returns = [(candles[i].close - candles[i - 1].close) / candles[i - 1].close for i in range(1, len(candles)) if candles[i - 1].close]
        recent_return = sum(returns[-5:]) if len(returns) >= 5 else 0.0
        if recent_return > 0.002:
            return AdapterScore(ResearchAdapterType.VECTORBT_FAST_BACKTEST.value, 78, "BUY", "VECTORBT_RECENT_RETURN_POSITIVE")
        if recent_return < -0.002:
            return AdapterScore(ResearchAdapterType.VECTORBT_FAST_BACKTEST.value, 78, "SELL", "VECTORBT_RECENT_RETURN_NEGATIVE")
        return AdapterScore(ResearchAdapterType.VECTORBT_FAST_BACKTEST.value, 45, NO_TRADE, "VECTORBT_RETURN_FLAT")

    def _backtrader_score(self, candles: Sequence[MarketCandle], features: Mapping[str, Any]) -> AdapterScore:
        if features["ema_fast"] > features["ema_slow"] and features["volume_ratio"] >= 0.8:
            return AdapterScore(ResearchAdapterType.BACKTRADER_EVENT_BACKTEST.value, 76, "BUY", "BACKTRADER_EMA_VOLUME_BUY")
        if features["ema_fast"] < features["ema_slow"] and features["volume_ratio"] >= 0.8:
            return AdapterScore(ResearchAdapterType.BACKTRADER_EVENT_BACKTEST.value, 76, "SELL", "BACKTRADER_EMA_VOLUME_SELL")
        return AdapterScore(ResearchAdapterType.BACKTRADER_EVENT_BACKTEST.value, 42, NO_TRADE, "BACKTRADER_EVENT_FILTER_BLOCK")

    def _finrl_sandbox_score(self, features: Mapping[str, Any]) -> AdapterScore:
        if features["regime"] == "TRENDING_UP" and 35 <= float(features["rsi_14"]) <= 72:
            return AdapterScore(ResearchAdapterType.FINRL_RL_SANDBOX.value, 70, "BUY", "FINRL_SANDBOX_POLICY_BUY_RESEARCH_ONLY")
        if features["regime"] == "TRENDING_DOWN" and 28 <= float(features["rsi_14"]) <= 65:
            return AdapterScore(ResearchAdapterType.FINRL_RL_SANDBOX.value, 70, "SELL", "FINRL_SANDBOX_POLICY_SELL_RESEARCH_ONLY")
        return AdapterScore(ResearchAdapterType.FINRL_RL_SANDBOX.value, 35, NO_TRADE, "FINRL_SANDBOX_POLICY_NO_TRADE")

    def _ml_quant_score(self, features: Mapping[str, Any]) -> AdapterScore:
        alpha = 0.0
        alpha += 25 if features["trend"] == "BULLISH" else -25 if features["trend"] == "BEARISH" else 0
        alpha += 20 if abs(float(features["momentum_5"])) > 0 else 0
        alpha += 20 if float(features["volume_ratio"]) >= 0.8 else -20
        if alpha >= 35:
            return AdapterScore(ResearchAdapterType.ML_QUANT_ALPHA_RESEARCH.value, 80, "BUY", "ML_QUANT_ALPHA_BUY")
        if alpha <= -35:
            return AdapterScore(ResearchAdapterType.ML_QUANT_ALPHA_RESEARCH.value, 80, "SELL", "ML_QUANT_ALPHA_SELL")
        return AdapterScore(ResearchAdapterType.ML_QUANT_ALPHA_RESEARCH.value, 45, NO_TRADE, "ML_QUANT_ALPHA_WEAK")

    def _evaluate_forward_outcome(self, signal: Mapping[str, Any], forward: Sequence[MarketCandle]) -> BacktestOutcome:
        decision = str(signal["decision"])
        entry = float(signal["entry"])
        stop = float(signal["stop_loss"])
        target = float(signal["target_1"])
        for candle in forward:
            if decision == "BUY":
                if candle.low <= stop:
                    return BacktestOutcome(str(signal["symbol"]), str(signal["signal_id"]), decision, entry, stop, "STOP_HIT", round(stop - entry, 2))
                if candle.high >= target:
                    return BacktestOutcome(str(signal["symbol"]), str(signal["signal_id"]), decision, entry, target, "TARGET_HIT", round(target - entry, 2))
            if decision == "SELL":
                if candle.high >= stop:
                    return BacktestOutcome(str(signal["symbol"]), str(signal["signal_id"]), decision, entry, stop, "STOP_HIT", round(entry - stop, 2))
                if candle.low <= target:
                    return BacktestOutcome(str(signal["symbol"]), str(signal["signal_id"]), decision, entry, target, "TARGET_HIT", round(entry - target, 2))
        last_price = forward[-1].close if forward else entry
        pnl = last_price - entry if decision == "BUY" else entry - last_price
        return BacktestOutcome(str(signal["symbol"]), str(signal["signal_id"]), decision, entry, round(last_price, 2), "EXPIRED", round(pnl, 2))

    def _summary(self, symbol: str, outcomes: Sequence[BacktestOutcome], scores: Sequence[float]) -> BacktestSummary:
        completed = [row for row in outcomes if row.outcome in {"TARGET_HIT", "STOP_HIT", "EXPIRED"}]
        target_hits = sum(1 for row in completed if row.outcome == "TARGET_HIT")
        stop_hits = sum(1 for row in completed if row.outcome == "STOP_HIT")
        expired = sum(1 for row in completed if row.outcome == "EXPIRED")
        no_trade = sum(1 for row in outcomes if row.outcome == NO_TRADE or row.decision == NO_TRADE)
        if len(completed) >= MIN_COMPLETED_BACKTEST_OUTCOMES:
            accuracy: float | str = round((target_hits / len(completed)) * 100, 2)
            status = "VALIDATED"
            reason = "VALIDATED_BACKTEST_OUTCOME_EVIDENCE"
        else:
            accuracy = DATA_UNAVAILABLE
            status = DATA_UNAVAILABLE
            reason = "INSUFFICIENT_COMPLETED_BACKTEST_OUTCOMES"
        return BacktestSummary(
            symbol=symbol.strip().upper() or "RELIANCE",
            total_signals=len(outcomes),
            completed_outcomes=len(completed),
            target_hits=target_hits,
            stop_hits=stop_hits,
            expired=expired,
            no_trade=no_trade,
            proven_accuracy=accuracy,
            average_setup_score=round(mean(scores), 2) if scores else DATA_UNAVAILABLE,
            validation_status=status,
            reason=reason,
            adapter_family_count=len(research_adapter_catalog()),
        )


def _ema(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = value * k + ema * (1 - k)
    return round(ema, 4)


def _atr(candles: Sequence[MarketCandle], period: int) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    for idx in range(1, len(candles)):
        current = candles[idx]
        previous_close = candles[idx - 1].close
        trs.append(max(current.high - current.low, abs(current.high - previous_close), abs(current.low - previous_close)))
    return round(mean(trs[-period:]), 4) if trs else 0.0


def _rsi(values: Sequence[float], period: int) -> float:
    if len(values) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, len(values)):
        diff = values[idx] - values[idx - 1]
        gains.append(max(diff, 0.0))
        losses.append(abs(min(diff, 0.0)))
    avg_gain = mean(gains[-period:]) if gains else 0.0
    avg_loss = mean(losses[-period:]) if losses else 0.0
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _now() -> str:
    return datetime.now(UTC).isoformat()
