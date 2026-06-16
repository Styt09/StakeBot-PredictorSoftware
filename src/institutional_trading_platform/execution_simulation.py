"""Phase 15 execution realism, slippage, latency, and microstructure simulation.

This module never routes orders to a broker. It produces deterministic
paper/shadow execution-quality evidence so validation does not rely on idealized
fills.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from math import ceil, floor, isfinite

from .alpha_gate_x import AlphaSignal
from .market_data_spine import DataQualityStatus


class ExecutionMode(StrEnum):
    IDEALIZED = "IDEALIZED"
    CONSERVATIVE = "CONSERVATIVE"
    MICROSTRUCTURE_AWARE = "MICROSTRUCTURE_AWARE"


class SimulatedOrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class LatencyBucket(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DepthLevel:
    price: float
    quantity: int


@dataclass(frozen=True)
class OrderBookSnapshot:
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


@dataclass(frozen=True)
class ExecutionSimulationConfig:
    mode: ExecutionMode = ExecutionMode.CONSERVATIVE
    tick_size: float = 0.05
    fixed_slippage_bps: float = 2.0
    brokerage: float = 20.0
    transaction_charges_bps: float = 0.3
    stt_bps: float = 2.5
    high_latency_ms: int = 1_000
    critical_latency_ms: int = 3_000
    min_fill_ratio: float = 0.80
    max_slippage_bps: float = 15.0
    max_participation_rate: float = 0.10


@dataclass(frozen=True)
class LatencyModel:
    signal_generation_ms: int = 50
    order_preparation_ms: int = 100
    user_approval_ms: int = 0
    broker_round_trip_ms: int = 150
    websocket_tick_delay_ms: int = 50
    candle_finalization_delay_ms: int = 100

    def report(self, config: ExecutionSimulationConfig | None = None) -> "LatencyReport":
        config = config or ExecutionSimulationConfig()
        total = self.signal_generation_ms + self.order_preparation_ms + self.user_approval_ms + self.broker_round_trip_ms + self.websocket_tick_delay_ms + self.candle_finalization_delay_ms
        if total >= config.critical_latency_ms:
            bucket = LatencyBucket.CRITICAL
        elif total >= config.high_latency_ms:
            bucket = LatencyBucket.HIGH
        elif total >= 300:
            bucket = LatencyBucket.NORMAL
        else:
            bucket = LatencyBucket.LOW
        warning = bucket in {LatencyBucket.HIGH, LatencyBucket.CRITICAL}
        return LatencyReport(total, bucket, warning)


@dataclass(frozen=True)
class LatencyReport:
    total_decision_to_fill_ms: int
    latency_bucket: LatencyBucket
    latency_warning: bool


@dataclass(frozen=True)
class SlippageAssumptions:
    fixed_bps: float = 2.0
    volatility: float = 0.0
    spread: float = 0.0
    average_traded_volume: int = 1
    visible_depth: int = 0
    impact_coefficient: float = 0.10


@dataclass(frozen=True)
class SlippageReport:
    expected_fill_price: float
    worst_case_fill_price: float
    slippage_cost: float
    slippage_bps: float
    slippage_warning: bool
    components: dict[str, float]


@dataclass(frozen=True)
class MarketImpactReport:
    participation_rate: float
    impact_bps: float
    impact_cost: float
    high_impact_order: bool
    low_liquidity_order: bool
    impossible_fill_assumption: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionQualityReport:
    requested_quantity: int
    filled_quantity: int
    fill_ratio: float
    expected_price: float | str
    realized_simulated_price: float | str
    spread_cost: float
    slippage_cost: float
    impact_cost: float
    fees: float
    total_execution_cost: float
    latency: LatencyReport
    warnings: tuple[str, ...]
    execution_quality_score: float
    data_status: str = "OK"
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["go_live_allowed"] = False
        return payload


@dataclass(frozen=True)
class ExecutionSimulationRequest:
    symbol: str
    side: AlphaSignal
    order_type: SimulatedOrderType
    quantity: int
    reference_price: float
    limit_price: float | None = None
    average_traded_volume: int = 1
    volatility: float = 0.0
    spread: float = 0.0
    depth: OrderBookSnapshot | None = None


class ExecutionSimulator:
    """Deterministic paper/shadow execution simulator."""

    def __init__(self, config: ExecutionSimulationConfig | None = None) -> None:
        self.config = config or ExecutionSimulationConfig()

    def simulate(self, request: ExecutionSimulationRequest, latency: LatencyModel | None = None) -> ExecutionQualityReport:
        if request.quantity <= 0 or request.reference_price <= 0:
            raise ValueError("quantity and reference price must be positive")
        latency_report = (latency or LatencyModel()).report(self.config)
        if self.config.mode == ExecutionMode.MICROSTRUCTURE_AWARE and request.depth is None:
            return ExecutionQualityReport(request.quantity, 0, 0.0, DataQualityStatus.DATA_UNAVAILABLE.value, DataQualityStatus.DATA_UNAVAILABLE.value, 0.0, 0.0, 0.0, 0.0, 0.0, latency_report, ("order book depth DATA_UNAVAILABLE",), 0.0, DataQualityStatus.DATA_UNAVAILABLE.value, False)
        filled_qty, avg_price, depth_warnings = self._fill(request)
        fill_ratio = filled_qty / request.quantity
        slippage = calculate_slippage(request.side, request.reference_price, request.quantity, request.average_traded_volume, SlippageAssumptions(self.config.fixed_slippage_bps, request.volatility, request.spread, request.average_traded_volume, self._visible_depth(request.depth)))
        impact = estimate_market_impact(request.quantity, request.average_traded_volume, self._visible_depth(request.depth), request.spread, request.volatility, self.config.max_participation_rate, request.reference_price)
        spread_cost = abs(request.spread) * filled_qty / 2.0
        fees = self._fees(avg_price if isinstance(avg_price, float) else request.reference_price, filled_qty)
        realized = avg_price if filled_qty else ("MISSED_FILL" if request.order_type == SimulatedOrderType.LIMIT else request.reference_price)
        warnings = list(depth_warnings) + list(impact.warnings)
        if fill_ratio < self.config.min_fill_ratio:
            warnings.append("low fill ratio")
        if slippage.slippage_warning:
            warnings.append("slippage threshold warning")
        if latency_report.latency_warning:
            warnings.append("latency warning")
        if impact.impossible_fill_assumption:
            warnings.append("impossible fill assumption")
        total_cost = spread_cost + slippage.slippage_cost + impact.impact_cost + fees
        score = max(0.0, 100.0 - (100.0 * (1 - fill_ratio)) - min(slippage.slippage_bps, 50.0) - min(impact.impact_bps, 50.0) - (25.0 if latency_report.latency_warning else 0.0) - (50.0 if impact.impossible_fill_assumption else 0.0))
        return ExecutionQualityReport(request.quantity, filled_qty, fill_ratio, slippage.expected_fill_price, realized, spread_cost, slippage.slippage_cost, impact.impact_cost, fees, total_cost, latency_report, tuple(warnings), round(score, 2), "OK", False)

    def _fill(self, request: ExecutionSimulationRequest) -> tuple[int, float, tuple[str, ...]]:
        if self.config.mode == ExecutionMode.IDEALIZED:
            return request.quantity, round_to_tick(request.reference_price, self.config.tick_size, request.side), ("idealized execution mode",)
        if request.depth is not None:
            return self._depth_fill(request)
        if request.order_type == SimulatedOrderType.LIMIT and request.limit_price is not None:
            marketable = request.reference_price <= request.limit_price if request.side == AlphaSignal.BUY else request.reference_price >= request.limit_price
            if not marketable:
                return 0, request.reference_price, ("missed limit fill",)
        adverse = 1 if request.side == AlphaSignal.BUY else -1
        price = request.reference_price + adverse * max(request.spread / 2.0, request.reference_price * self.config.fixed_slippage_bps / 10_000.0)
        return request.quantity, round_to_tick(price, self.config.tick_size, request.side), ()

    def _depth_fill(self, request: ExecutionSimulationRequest) -> tuple[int, float, tuple[str, ...]]:
        levels = request.depth.asks if request.side == AlphaSignal.BUY else request.depth.bids  # type: ignore[union-attr]
        if not levels:
            return 0, request.reference_price, ("order book depth DATA_UNAVAILABLE",)
        remaining = request.quantity
        filled = 0
        notional = 0.0
        for level in levels[:5]:
            if request.order_type == SimulatedOrderType.LIMIT and request.limit_price is not None:
                if request.side == AlphaSignal.BUY and level.price > request.limit_price:
                    break
                if request.side == AlphaSignal.SELL and level.price < request.limit_price:
                    break
            qty = min(remaining, level.quantity)
            filled += qty
            remaining -= qty
            notional += qty * level.price
            if remaining == 0:
                break
        warnings = () if filled == request.quantity else ("partial fill",) if filled else ("missed fill",)
        avg = notional / filled if filled else request.reference_price
        return filled, round_to_tick(avg, self.config.tick_size, request.side), warnings

    def _visible_depth(self, depth: OrderBookSnapshot | None) -> int:
        if depth is None:
            return 0
        return sum(level.quantity for level in depth.bids[:5] + depth.asks[:5])

    def _fees(self, price: float, quantity: int) -> float:
        notional = price * quantity
        return self.config.brokerage + notional * ((self.config.transaction_charges_bps + self.config.stt_bps) / 10_000.0)


def calculate_slippage(side: AlphaSignal, reference_price: float, quantity: int, average_traded_volume: int, assumptions: SlippageAssumptions) -> SlippageReport:
    fixed = assumptions.fixed_bps
    volatility = max(0.0, assumptions.volatility) * 10.0
    spread = (assumptions.spread / reference_price * 10_000.0) if reference_price and assumptions.spread else 0.0
    liquidity = (quantity / max(average_traded_volume, 1)) * 100.0
    impact = assumptions.impact_coefficient * liquidity
    total_bps = fixed + volatility + spread + liquidity + impact
    adverse = 1 if side == AlphaSignal.BUY else -1
    expected = reference_price * (1 + adverse * total_bps / 10_000.0)
    worst = reference_price * (1 + adverse * (total_bps * 1.5) / 10_000.0)
    cost = abs(expected - reference_price) * quantity
    return SlippageReport(expected, worst, cost, total_bps, total_bps > 15.0, {"fixed_bps": fixed, "volatility_bps": volatility, "spread_bps": spread, "liquidity_bps": liquidity, "impact_bps": impact})


def estimate_market_impact(quantity: int, average_traded_volume: int, visible_depth: int, spread: float, volatility: float, max_participation_rate: float, reference_price: float) -> MarketImpactReport:
    participation = quantity / max(average_traded_volume, 1)
    depth_ratio = quantity / max(visible_depth, 1) if visible_depth else float("inf")
    impact_bps = (participation * 100.0) + (0.0 if depth_ratio == float("inf") else depth_ratio * 10.0) + max(volatility, 0.0) * 10.0 + ((spread / reference_price * 10_000.0) if reference_price and spread else 0.0)
    warnings: list[str] = []
    high = participation > max_participation_rate
    low_liq = visible_depth == 0 or depth_ratio > 1.0
    impossible = visible_depth > 0 and quantity > visible_depth * 5
    if high:
        warnings.append("high-impact order")
    if low_liq:
        warnings.append("low-liquidity order")
    if impossible:
        warnings.append("impossible fill assumption")
    return MarketImpactReport(participation, impact_bps, reference_price * quantity * impact_bps / 10_000.0, high, low_liq, impossible, tuple(warnings))


def round_to_tick(price: float, tick_size: float, side: AlphaSignal) -> float:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    ticks = price / tick_size
    rounded_ticks = ceil(ticks) if side == AlphaSignal.BUY else floor(ticks)
    return round(rounded_ticks * tick_size, 10)


def execution_realism_evidence_section(reports: tuple[ExecutionQualityReport, ...], assumptions: dict[str, object] | None = None) -> dict[str, object]:
    assumptions = assumptions or {}
    fill_ratio = sum(report.filled_quantity for report in reports) / max(sum(report.requested_quantity for report in reports), 1)
    score = sum(report.execution_quality_score for report in reports) / len(reports) if reports else 0.0
    warnings = tuple(warning for report in reports for warning in report.warnings)
    return {
        "execution_reports": tuple(report.to_dict() for report in reports),
        "latency_reports": tuple(asdict(report.latency) for report in reports),
        "slippage_assumptions": assumptions,
        "impact_warnings": tuple(warning for warning in warnings if "impact" in warning or "liquidity" in warning or "impossible" in warning),
        "fill_realism_score": score,
        "fill_ratio": fill_ratio,
        "warnings": warnings,
        "go_live_allowed": False,
    }
