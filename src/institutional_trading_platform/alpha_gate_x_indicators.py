"""Phase 3 indicator integration for ALPHA-GATE X signal generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from .alpha_gate_x import AlphaGateXEngine, AlphaSignal, FactorScores, MarketRegime, RiskDecision, RiskStatus
from .indicators.atr import atr, atr_stop_loss, atr_targets, expected_move
from .indicators.common import IndicatorResult
from .indicators.liquidity_sweep import liquidity_sweep_score
from .indicators.market_breadth import MarketBreadthSnapshot, market_breadth_score
from .indicators.order_book_imbalance import order_book_imbalance_score
from .indicators.trend_regime import TrendRegimeLabel, trend_regime
from .indicators.volume_confirmation import volume_confirmation_score
from .indicators.vwap import vwap_pressure_score
from .market_data_spine import DataQualityReport, DataQualityStatus, MarketDepth, OHLCVCandle, completed_candles_for_signal


class TradingProfile(StrEnum):
    """Signal profile selection for Phase 3 indicator composition."""

    INTRADAY = "INTRADAY"
    SWING = "SWING"


class ConfidenceGrade(StrEnum):
    """Human-readable confidence grade."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class IndicatorSignalOutput:
    """Full Phase 3 signal output with component-level evidence."""

    symbol: str
    timeframe: str
    trading_profile: TradingProfile
    signal: AlphaSignal
    final_score: float
    confidence: float
    confidence_grade: ConfidenceGrade
    entry_reference: float | None
    stop_loss: float | None
    target_1: float | None
    target_2: float | None
    expected_move: float | None
    risk_status: RiskStatus
    component_scores: dict[str, float]
    unavailable_components: tuple[str, ...]
    reasons: tuple[str, ...]
    correlation_id: str

    @property
    def is_tradeable(self) -> bool:
        """Return whether this signal is actionable after Phase 3 checks."""

        return self.signal in {AlphaSignal.BUY, AlphaSignal.SELL} and self.risk_status == RiskStatus.PASS


@dataclass(frozen=True)
class IndicatorContext:
    """Optional external indicator inputs unavailable from candles."""

    depth: MarketDepth | None = None
    breadth: MarketBreadthSnapshot | None = None
    data_quality: DataQualityReport | None = None
    allow_incomplete: bool = False
    first_five_minutes_blocked: bool = False


class IndicatorSignalComposer:
    """Compose deterministic indicators into the existing ALPHA-GATE X formula."""

    CRITICAL_COMPONENTS = {"trend_regime", "vwap_pressure", "volume_confirmation"}

    def __init__(self, engine: AlphaGateXEngine | None = None) -> None:
        self.engine = engine or AlphaGateXEngine()

    def intraday_signal(
        self,
        *,
        symbol: str,
        exchange: str,
        one_minute: tuple[OHLCVCandle, ...],
        five_minute: tuple[OHLCVCandle, ...],
        fifteen_minute: tuple[OHLCVCandle, ...],
        risk_decision: RiskDecision,
        context: IndicatorContext | None = None,
        correlation_id: str | None = None,
    ) -> IndicatorSignalOutput:
        """Build an intraday signal: 15m trend, 5m confirmation, 1m execution context."""

        del one_minute  # 1m is intentionally excluded from score generation in Phase 3.
        context = context or IndicatorContext()
        trend_candles = completed_candles_for_signal(fifteen_minute, context.allow_incomplete)
        entry_candles = completed_candles_for_signal(five_minute, context.allow_incomplete)
        return self._compose(
            symbol=symbol,
            exchange=exchange,
            timeframe="5m",
            profile=TradingProfile.INTRADAY,
            trend_candles=trend_candles,
            entry_candles=entry_candles,
            risk_decision=risk_decision,
            context=context,
            correlation_id=correlation_id,
        )

    def swing_signal(
        self,
        *,
        symbol: str,
        exchange: str,
        daily: tuple[OHLCVCandle, ...],
        hourly: tuple[OHLCVCandle, ...],
        risk_decision: RiskDecision,
        context: IndicatorContext | None = None,
        correlation_id: str | None = None,
    ) -> IndicatorSignalOutput:
        """Build a swing signal: Daily trend and 1H entry confirmation."""

        context = context or IndicatorContext()
        trend_candles = completed_candles_for_signal(daily, context.allow_incomplete)
        entry_candles = completed_candles_for_signal(hourly, context.allow_incomplete)
        return self._compose(
            symbol=symbol,
            exchange=exchange,
            timeframe="1H",
            profile=TradingProfile.SWING,
            trend_candles=trend_candles,
            entry_candles=entry_candles,
            risk_decision=risk_decision,
            context=context,
            correlation_id=correlation_id,
        )

    def _compose(
        self,
        *,
        symbol: str,
        exchange: str,
        timeframe: str,
        profile: TradingProfile,
        trend_candles: tuple[OHLCVCandle, ...],
        entry_candles: tuple[OHLCVCandle, ...],
        risk_decision: RiskDecision,
        context: IndicatorContext,
        correlation_id: str | None,
    ) -> IndicatorSignalOutput:
        results = {
            "trend_regime": trend_regime(trend_candles),
            "liquidity_sweep": liquidity_sweep_score(entry_candles),
            "vwap_pressure": vwap_pressure_score(entry_candles),
            "order_book_imbalance": order_book_imbalance_score(context.depth),
            "volume_confirmation": volume_confirmation_score(entry_candles),
            "market_breadth": market_breadth_score(context.breadth),
        }
        unavailable_components = tuple(name for name, result in results.items() if not result.available)
        component_scores = {name: result.score for name, result in results.items()}
        reasons = self._reasons(results)
        latest = entry_candles[-1] if entry_candles else None
        atr_result = atr(entry_candles)
        expected = expected_move(entry_candles)
        data_block = context.data_quality is not None and context.data_quality.status in {DataQualityStatus.FAIL, DataQualityStatus.DATA_UNAVAILABLE}
        critical_unavailable = any(name in unavailable_components for name in self.CRITICAL_COMPONENTS)
        danger = self._is_danger(results["trend_regime"])
        risk = risk_decision
        if data_block:
            risk = RiskDecision(RiskStatus.FAIL, 0, 0.0, context.data_quality.reasons or (context.data_quality.status.value,))
            reasons.extend(f"data quality block: {reason}" for reason in risk.reasons)
        if context.first_five_minutes_blocked:
            risk = RiskDecision(RiskStatus.FAIL, 0, 0.0, risk.reasons + ("first 5 minutes blocked",))
            reasons.append("first 5 minutes blocked")
        factors = FactorScores(
            trend_regime=component_scores["trend_regime"],
            liquidity_sweep=component_scores["liquidity_sweep"],
            vwap_pressure=component_scores["vwap_pressure"],
            order_book_imbalance=component_scores["order_book_imbalance"],
            volume_confirmation=component_scores["volume_confirmation"],
            market_breadth=component_scores["market_breadth"],
        )
        market_regime = MarketRegime.DANGER if danger else MarketRegime.NEUTRAL
        base = self.engine.evaluate(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            factors=factors,
            risk_decision=risk,
            market_regime=market_regime,
            entry=latest.close if latest else None,
            stop_loss=None,
            target_1=None,
            target_2=None,
            correlation_id=correlation_id or f"agx3-{uuid4()}",
        )
        signal = base.signal
        if critical_unavailable and signal in {AlphaSignal.BUY, AlphaSignal.SELL}:
            signal = AlphaSignal.HOLD
            reasons.append("critical indicator unavailable; actionable signal downgraded to HOLD")
        if unavailable_components and signal in {AlphaSignal.BUY, AlphaSignal.SELL} and base.confidence < 0.80:
            signal = AlphaSignal.HOLD
            reasons.append("non-critical unavailable components reduce confidence below actionable threshold")
        confidence = self._confidence(base.confidence, unavailable_components, critical_unavailable, data_block or danger)
        side = "BUY" if base.final_score >= 0 else "SELL"
        stop_loss = target_1 = target_2 = None
        if latest is not None and atr_result.available and signal in {AlphaSignal.BUY, AlphaSignal.SELL}:
            stop_loss = atr_stop_loss(latest.close, signal.value, atr_result.score)
            target_1, target_2 = atr_targets(latest.close, signal.value, atr_result.score)
        return IndicatorSignalOutput(
            symbol=symbol,
            timeframe=timeframe,
            trading_profile=profile,
            signal=signal,
            final_score=base.final_score,
            confidence=confidence,
            confidence_grade=self._confidence_grade(confidence),
            entry_reference=latest.close if latest else None,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            expected_move=expected.score if expected.available else None,
            risk_status=risk.status,
            component_scores=component_scores,
            unavailable_components=unavailable_components,
            reasons=tuple(reasons + list(base.reasons)),
            correlation_id=base.correlation_id,
        )

    @staticmethod
    def _reasons(results: dict[str, IndicatorResult]) -> list[str]:
        reasons: list[str] = []
        for name, result in results.items():
            if result.available:
                reasons.extend(f"{name}: {reason}" for reason in result.reasons)
            else:
                reasons.extend(f"{name} unavailable: {reason}" for reason in result.reasons)
        return reasons

    @staticmethod
    def _is_danger(result: IndicatorResult) -> bool:
        return any(TrendRegimeLabel.DANGER.value in reason for reason in result.reasons)

    @staticmethod
    def _confidence(base_confidence: float, unavailable_components: tuple[str, ...], critical_unavailable: bool, blocked: bool) -> float:
        confidence = base_confidence * max(0.0, 1.0 - 0.10 * len(unavailable_components))
        if critical_unavailable:
            confidence *= 0.5
        if blocked:
            confidence = min(confidence, 0.2)
        return round(max(0.0, min(1.0, confidence)), 4)

    @staticmethod
    def _confidence_grade(confidence: float) -> ConfidenceGrade:
        if confidence >= 0.80:
            return ConfidenceGrade.A
        if confidence >= 0.65:
            return ConfidenceGrade.B
        if confidence >= 0.50:
            return ConfidenceGrade.C
        return ConfidenceGrade.D
