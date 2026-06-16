"""ALPHA-GATE X auto-trading primitives.

This module provides a conservative, broker-neutral implementation of the
ALPHA-GATE X blueprint: deterministic signal scoring, mandatory risk gating,
paper-only mode controls, duplicate-order prevention, and an auditable order
state machine.  This repository permanently forbids live broker order
placement; ``LIVE_AUTO`` is retained only as a rejected compatibility enum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import StrEnum
from math import floor
from os import environ
from uuid import uuid4


class TradingMode(StrEnum):
    """Supported ALPHA-GATE X operating modes."""

    BACKTEST = "BACKTEST"
    PAPER_TRADING = "PAPER_TRADING"
    APPROVAL_MODE = "APPROVAL_MODE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LIVE_AUTO = "LIVE_AUTO"


class RealOrderPathForbidden(ValueError):
    """Raised whenever code attempts to create or use a real-order path."""


class AlphaSignal(StrEnum):
    """Signal outcomes emitted by ALPHA-GATE X."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


class RiskStatus(StrEnum):
    """Risk gate status values."""

    PASS = "PASS"
    FAIL = "FAIL"


class MarketRegime(StrEnum):
    """Market-regime labels used by the no-trade filter."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    DANGER = "DANGER"


class OrderState(StrEnum):
    """Order lifecycle states used for audit and reconciliation."""

    SIGNAL_CREATED = "SIGNAL_CREATED"
    RISK_CHECK_PENDING = "RISK_CHECK_PENDING"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_OPEN = "ORDER_OPEN"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    POSITION_OPEN = "POSITION_OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    POSITION_CLOSED = "POSITION_CLOSED"


@dataclass(frozen=True)
class AlphaGateXSettings:
    """Runtime settings with paper-trading defaults and live-trading guardrails."""

    trading_mode: TradingMode = TradingMode.PAPER_TRADING
    live_trading: bool = False
    database_url: str = "postgresql://user:password@localhost:5432/alpha_gate_x"
    redis_url: str = "redis://localhost:6379/0"
    zerodha_api_key: str = ""
    zerodha_redirect_url: str = "http://localhost:8000/auth/zerodha/callback"

    @classmethod
    def from_env(cls) -> "AlphaGateXSettings":
        """Load settings from environment variables with safe defaults."""

        raw_mode = environ.get("TRADING_MODE", TradingMode.PAPER_TRADING.value).strip() or TradingMode.PAPER_TRADING.value
        live_flag = environ.get("LIVE_TRADING", "false").strip().lower() in {"1", "true", "yes", "on"}
        mode = TradingMode(raw_mode)
        settings = cls(
            trading_mode=mode,
            live_trading=live_flag,
            database_url=environ.get("DATABASE_URL", cls.database_url),
            redis_url=environ.get("REDIS_URL", cls.redis_url),
            zerodha_api_key=environ.get("ZERODHA_API_KEY", ""),
            zerodha_redirect_url=environ.get("ZERODHA_REDIRECT_URL", cls.zerodha_redirect_url),
        )
        settings.validate_live_trading()
        return settings

    @property
    def live_orders_enabled(self) -> bool:
        """Return whether live broker orders may be sent.

        This repository is intentionally incapable of enabling real broker
        orders.  The property always returns ``False`` so static and runtime
        checks agree that no live order path exists.
        """

        return False

    def validate_live_trading(self) -> None:
        """Reject unsafe live-trading configuration."""

        if self.trading_mode == TradingMode.LIVE_AUTO:
            raise RealOrderPathForbidden("rejects LIVE_AUTO: real order placement is permanently forbidden in this repository")


@dataclass(frozen=True)
class FactorScores:
    """Normalized ALPHA-GATE X factor scores in the inclusive range [-1, 1]."""

    trend_regime: float
    liquidity_sweep: float
    vwap_pressure: float
    order_book_imbalance: float
    volume_confirmation: float
    market_breadth: float

    def validate(self) -> None:
        """Validate all score ranges before weighted scoring."""

        for name, value in self.__dict__.items():
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between -1 and 1")


@dataclass(frozen=True)
class AlphaGateXSignal:
    """Auditable signal payload produced by the ALPHA-GATE X signal engine."""

    correlation_id: str
    symbol: str
    exchange: str
    timeframe: str
    signal: AlphaSignal
    confidence: float
    final_score: float
    entry: float | None
    stop_loss: float | None
    target_1: float | None
    target_2: float | None
    risk_status: RiskStatus
    reasons: tuple[str, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_actionable(self) -> bool:
        """Return whether this signal can progress to execution checks."""

        return self.signal in {AlphaSignal.BUY, AlphaSignal.SELL} and self.risk_status == RiskStatus.PASS


@dataclass(frozen=True)
class RiskConfig:
    """Configurable pre-trade risk limits."""

    capital: float = 50_000.0
    risk_per_trade_percent: float = 0.5
    max_daily_loss_percent: float = 1.0
    max_weekly_loss_percent: float = 3.0
    max_monthly_loss_percent: float = 5.0
    max_trades_per_day: int = 5
    max_order_quantity: int = 10
    max_open_positions: int = 2
    max_symbol_exposure_percent: float = 20.0
    max_sector_exposure_percent: float = 40.0
    max_spread_percent: float = 0.15
    min_volume: float = 100_000.0
    max_realized_volatility: float = 0.08

    def validate(self) -> None:
        """Validate configured limits."""

        if self.capital <= 0:
            raise ValueError("capital must be positive")
        if not 0.25 <= self.risk_per_trade_percent <= 0.75:
            raise ValueError("risk_per_trade_percent must be between 0.25 and 0.75")
        if not 0 < self.max_daily_loss_percent <= 2.0:
            raise ValueError("max_daily_loss_percent must be between 0 and 2")
        if not self.max_daily_loss_percent <= self.max_weekly_loss_percent <= 10.0:
            raise ValueError("max_weekly_loss_percent must be at least daily loss and at most 10")
        if not self.max_weekly_loss_percent <= self.max_monthly_loss_percent <= 20.0:
            raise ValueError("max_monthly_loss_percent must be at least weekly loss and at most 20")
        if self.max_trades_per_day <= 0 or self.max_order_quantity <= 0 or self.max_open_positions <= 0:
            raise ValueError("trade, quantity, and position limits must be positive")
        if not 0 < self.max_symbol_exposure_percent <= 100:
            raise ValueError("max_symbol_exposure_percent must be between 0 and 100")
        if not self.max_symbol_exposure_percent <= self.max_sector_exposure_percent <= 100:
            raise ValueError("max_sector_exposure_percent must be at least symbol exposure and at most 100")


@dataclass(frozen=True)
class RiskContext:
    """Current risk facts required before an order can be routed."""

    daily_realized_loss: float = 0.0
    weekly_realized_loss: float = 0.0
    monthly_realized_loss: float = 0.0
    trades_today: int = 0
    open_positions: int = 0
    symbol_exposure_value: float = 0.0
    sector_exposure_value: float = 0.0
    spread_percent: float = 0.0
    average_volume: float = 0.0
    realized_volatility: float = 0.0
    broker_connected: bool = True
    market_data_stale: bool = False
    kill_switch_active: bool = False
    current_time: time | None = None
    enable_first_5_min_trading: bool = False


@dataclass(frozen=True)
class RiskDecision:
    """Risk gate result with executable quantity and rejection reasons."""

    status: RiskStatus
    quantity: int
    risk_amount: float
    reasons: tuple[str, ...]

    @property
    def approved(self) -> bool:
        """Return whether the risk gate approved the trade."""

        return self.status == RiskStatus.PASS


class PositionSizer:
    """Risk-per-trade position sizing."""

    @staticmethod
    def quantity(capital: float, risk_per_trade_percent: float, entry: float, stop_loss: float, max_quantity: int) -> int:
        """Calculate quantity from capital risk and stop distance."""

        if capital <= 0 or risk_per_trade_percent <= 0 or entry <= 0 or stop_loss <= 0 or max_quantity <= 0:
            raise ValueError("position sizing inputs must be positive")
        risk_per_share = abs(entry - stop_loss)
        if risk_per_share <= 0:
            raise ValueError("entry and stop_loss must differ")
        risk_amount = capital * (risk_per_trade_percent / 100.0)
        return max(0, min(max_quantity, floor(risk_amount / risk_per_share)))


class RiskGate:
    """Mandatory ALPHA-GATE X risk gate."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()
        self.config.validate()

    def assess(self, entry: float, stop_loss: float, context: RiskContext) -> RiskDecision:
        """Assess pre-trade limits and calculate an approved quantity."""

        reasons: list[str] = []
        max_daily_loss = self.config.capital * (self.config.max_daily_loss_percent / 100.0)
        max_weekly_loss = self.config.capital * (self.config.max_weekly_loss_percent / 100.0)
        max_monthly_loss = self.config.capital * (self.config.max_monthly_loss_percent / 100.0)
        max_symbol_exposure = self.config.capital * (self.config.max_symbol_exposure_percent / 100.0)
        max_sector_exposure = self.config.capital * (self.config.max_sector_exposure_percent / 100.0)
        if context.kill_switch_active:
            reasons.append("kill switch active")
        if not context.broker_connected:
            reasons.append("broker disconnected")
        if context.market_data_stale:
            reasons.append("market data stale")
        if context.daily_realized_loss >= max_daily_loss:
            reasons.append("daily loss limit hit")
        if context.weekly_realized_loss >= max_weekly_loss:
            reasons.append("weekly loss limit hit")
        if context.monthly_realized_loss >= max_monthly_loss:
            reasons.append("monthly loss limit hit")
        if context.trades_today >= self.config.max_trades_per_day:
            reasons.append("max trades per day hit")
        if context.open_positions >= self.config.max_open_positions:
            reasons.append("max open positions hit")
        if context.symbol_exposure_value >= max_symbol_exposure:
            reasons.append("symbol concentration limit hit")
        if context.sector_exposure_value >= max_sector_exposure:
            reasons.append("sector concentration limit hit")
        if context.spread_percent > self.config.max_spread_percent:
            reasons.append("spread too wide")
        if context.average_volume < self.config.min_volume:
            reasons.append("liquidity too low")
        if context.realized_volatility > self.config.max_realized_volatility:
            reasons.append("volatility abnormal")
        if self._is_first_five_minutes(context):
            reasons.append("first 5 minutes blocked")

        risk_amount = self.config.capital * (self.config.risk_per_trade_percent / 100.0)
        quantity = 0
        if not reasons:
            quantity = PositionSizer.quantity(
                self.config.capital,
                self.config.risk_per_trade_percent,
                entry,
                stop_loss,
                self.config.max_order_quantity,
            )
            if quantity <= 0:
                reasons.append("position size is zero")

        status = RiskStatus.FAIL if reasons else RiskStatus.PASS
        return RiskDecision(status=status, quantity=quantity if status == RiskStatus.PASS else 0, risk_amount=risk_amount, reasons=tuple(reasons))

    @staticmethod
    def _is_first_five_minutes(context: RiskContext) -> bool:
        if context.enable_first_5_min_trading or context.current_time is None:
            return False
        return time(9, 15) <= context.current_time < time(9, 20)


class AlphaGateXEngine:
    """Deterministic multi-factor ALPHA-GATE X signal engine."""

    WEIGHTS: dict[str, float] = {
        "trend_regime": 0.25,
        "liquidity_sweep": 0.20,
        "vwap_pressure": 0.15,
        "order_book_imbalance": 0.15,
        "volume_confirmation": 0.15,
        "market_breadth": 0.10,
    }

    def __init__(self, buy_threshold: float = 0.72, sell_threshold: float = -0.72) -> None:
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def evaluate(
        self,
        *,
        symbol: str,
        exchange: str,
        timeframe: str,
        factors: FactorScores,
        risk_decision: RiskDecision,
        market_regime: MarketRegime,
        entry: float | None,
        stop_loss: float | None,
        target_1: float | None,
        target_2: float | None,
        correlation_id: str | None = None,
    ) -> AlphaGateXSignal:
        """Return BUY, SELL, HOLD, or NO_TRADE using the blueprint formula."""

        factors.validate()
        final_score = self.final_score(factors)
        confidence = min(1.0, abs(final_score))
        reasons = self._factor_reasons(factors)
        signal = AlphaSignal.HOLD

        if risk_decision.status == RiskStatus.FAIL:
            signal = AlphaSignal.NO_TRADE
            reasons.extend(risk_decision.reasons)
        elif market_regime == MarketRegime.DANGER:
            signal = AlphaSignal.NO_TRADE
            reasons.append("market regime danger")
        elif final_score >= self.buy_threshold:
            signal = AlphaSignal.BUY
            reasons.append("final score crossed BUY threshold")
        elif final_score <= self.sell_threshold:
            signal = AlphaSignal.SELL
            reasons.append("final score crossed SELL threshold")
        else:
            reasons.append("score weak; hold")

        return AlphaGateXSignal(
            correlation_id=correlation_id or f"agx-{uuid4()}",
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            final_score=final_score,
            entry=entry,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_status=risk_decision.status,
            reasons=tuple(reasons),
        )

    @classmethod
    def final_score(cls, factors: FactorScores) -> float:
        """Calculate the weighted ALPHA-GATE X final score."""

        factors.validate()
        return round(sum(getattr(factors, name) * weight for name, weight in cls.WEIGHTS.items()), 6)

    @staticmethod
    def _factor_reasons(factors: FactorScores) -> list[str]:
        reasons: list[str] = []
        labels = {
            "trend_regime": "trend regime",
            "liquidity_sweep": "liquidity sweep",
            "vwap_pressure": "VWAP pressure",
            "order_book_imbalance": "order book imbalance",
            "volume_confirmation": "volume confirmation",
            "market_breadth": "market breadth",
        }
        for name, label in labels.items():
            value = getattr(factors, name)
            if value >= 0.5:
                reasons.append(f"{label} positive")
            elif value <= -0.5:
                reasons.append(f"{label} negative")
        return reasons


@dataclass(frozen=True)
class OrderRequest:
    """Broker-neutral order request."""

    correlation_id: str
    symbol: str
    side: AlphaSignal
    quantity: int
    order_type: str = "MARKET"
    product: str = "MIS"
    requested_price: float | None = None

    def validate(self) -> None:
        """Validate order request fields."""

        if self.side not in {AlphaSignal.BUY, AlphaSignal.SELL}:
            raise ValueError("order side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.requested_price is not None and self.requested_price <= 0:
            raise ValueError("requested_price must be positive when supplied")


@dataclass(frozen=True)
class OrderResult:
    """Broker-neutral order result."""

    correlation_id: str
    status: OrderState
    broker_order_id: str | None = None
    average_price: float | None = None
    rejection_reason: str | None = None


class DuplicateOrderGuard:
    """In-memory duplicate order prevention keyed by correlation id."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def register(self, correlation_id: str) -> bool:
        """Register an order correlation id; return False for duplicates."""

        if correlation_id in self._seen:
            return False
        self._seen.add(correlation_id)
        return True


class PaperBroker:
    """Paper broker that produces virtual fills without touching Zerodha."""

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Create a virtual fill for paper trading and backtesting."""

        request.validate()
        fill_price = request.requested_price
        return OrderResult(
            correlation_id=request.correlation_id,
            status=OrderState.ORDER_FILLED,
            broker_order_id=f"paper-{request.correlation_id}",
            average_price=fill_price,
        )


class OrderStateMachine:
    """Validate order lifecycle transitions."""

    ALLOWED: dict[OrderState, tuple[OrderState, ...]] = {
        OrderState.SIGNAL_CREATED: (OrderState.RISK_CHECK_PENDING,),
        OrderState.RISK_CHECK_PENDING: (OrderState.RISK_APPROVED, OrderState.RISK_REJECTED),
        OrderState.RISK_APPROVED: (OrderState.ORDER_PLACED,),
        OrderState.RISK_REJECTED: (),
        OrderState.ORDER_PLACED: (OrderState.ORDER_OPEN, OrderState.ORDER_FILLED, OrderState.ORDER_REJECTED, OrderState.ORDER_CANCELLED),
        OrderState.ORDER_OPEN: (OrderState.ORDER_FILLED, OrderState.ORDER_REJECTED, OrderState.ORDER_CANCELLED),
        OrderState.ORDER_FILLED: (OrderState.POSITION_OPEN,),
        OrderState.ORDER_REJECTED: (),
        OrderState.ORDER_CANCELLED: (),
        OrderState.POSITION_OPEN: (OrderState.EXIT_PENDING, OrderState.POSITION_CLOSED),
        OrderState.EXIT_PENDING: (OrderState.POSITION_CLOSED,),
        OrderState.POSITION_CLOSED: (),
    }

    def __init__(self) -> None:
        self.state = OrderState.SIGNAL_CREATED

    def transition(self, next_state: OrderState) -> OrderState:
        """Move to the next lifecycle state if allowed."""

        if next_state not in self.ALLOWED[self.state]:
            raise ValueError(f"invalid transition from {self.state} to {next_state}")
        self.state = next_state
        return self.state


class OrderRouter:
    """Route approved ALPHA-GATE X signals to paper adapters only."""

    def __init__(self, settings: AlphaGateXSettings, paper_broker: PaperBroker | None = None, live_broker: object | None = None) -> None:
        if live_broker is not None:
            raise RealOrderPathForbidden("live broker adapters are forbidden; use paper/preview-only services")
        self.settings = settings
        self.paper_broker = paper_broker or PaperBroker()
        self.live_broker = None
        self.duplicates = DuplicateOrderGuard()

    def route(self, signal: AlphaGateXSignal, risk_decision: RiskDecision, manual_approved: bool = False) -> OrderResult:
        """Route a signal after risk approval, approval-mode, and duplicate checks."""

        if not signal.is_actionable:
            return OrderResult(signal.correlation_id, OrderState.RISK_REJECTED, rejection_reason="signal is not actionable")
        if self.settings.trading_mode == TradingMode.APPROVAL_MODE and not manual_approved:
            return OrderResult(signal.correlation_id, OrderState.RISK_APPROVED, rejection_reason="manual approval required")
        if not self.duplicates.register(signal.correlation_id):
            return OrderResult(signal.correlation_id, OrderState.ORDER_REJECTED, rejection_reason="duplicate order blocked")
        request = OrderRequest(
            correlation_id=signal.correlation_id,
            symbol=signal.symbol,
            side=signal.signal,
            quantity=risk_decision.quantity,
            requested_price=signal.entry,
        )
        if self.settings.trading_mode in {TradingMode.PAPER_TRADING, TradingMode.BACKTEST, TradingMode.APPROVAL_MODE}:
            return self.paper_broker.place_order(request)
        raise RealOrderPathForbidden("real order routing is permanently forbidden")


def assert_real_order_path_forbidden() -> bool:
    """Runtime guard used by scripts/tests before any shadow-readiness check."""

    settings = AlphaGateXSettings()
    if settings.live_orders_enabled:
        raise RealOrderPathForbidden("live_orders_enabled must never be true")
    return True
