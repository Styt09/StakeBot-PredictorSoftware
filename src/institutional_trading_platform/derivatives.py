"""Derivatives analytics: Greeks, volatility surfaces, forecasting, and calibration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import erf, exp, isfinite, log, pi, sqrt
from statistics import fmean
from typing import Mapping, Sequence


class OptionType(StrEnum):
    """Option type."""

    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class Greeks:
    """Black-Scholes Greeks."""

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass(frozen=True)
class OptionContract:
    """Option input for pricing and Greeks."""

    option_type: OptionType
    spot: float
    strike: float
    time_to_expiry: float
    volatility: float
    risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        for name in ("spot", "strike", "time_to_expiry", "volatility"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not isfinite(self.risk_free_rate):
            raise ValueError("risk_free_rate must be finite")


def black_scholes_price(contract: OptionContract) -> float:
    """Black-Scholes option price."""

    d1, d2 = _d1_d2(contract)
    if contract.option_type == OptionType.CALL:
        return contract.spot * _cdf(d1) - contract.strike * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(d2)
    return contract.strike * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(-d2) - contract.spot * _cdf(-d1)


def greeks(contract: OptionContract) -> Greeks:
    """Compute Black-Scholes Greeks."""

    d1, d2 = _d1_d2(contract)
    pdf = _pdf(d1)
    sign = 1 if contract.option_type == OptionType.CALL else -1
    delta = _cdf(d1) if contract.option_type == OptionType.CALL else _cdf(d1) - 1
    gamma = pdf / (contract.spot * contract.volatility * sqrt(contract.time_to_expiry))
    theta = -contract.spot * pdf * contract.volatility / (2 * sqrt(contract.time_to_expiry)) - sign * contract.risk_free_rate * contract.strike * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(sign * d2)
    vega = contract.spot * pdf * sqrt(contract.time_to_expiry)
    rho = sign * contract.strike * contract.time_to_expiry * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(sign * d2)
    return Greeks(delta, gamma, theta, vega, rho)


@dataclass(frozen=True)
class VolatilitySurface:
    """Sparse volatility surface indexed by (strike, maturity)."""

    nodes: Mapping[tuple[float, float], float]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("surface nodes are required")
        for (strike, maturity), volatility in self.nodes.items():
            if strike <= 0 or maturity <= 0 or volatility <= 0:
                raise ValueError("surface strikes, maturities, and vols must be positive")

    def volatility(self, strike: float, maturity: float) -> float:
        """Nearest-neighbor volatility lookup for sparse calibrated surfaces."""

        if strike <= 0 or maturity <= 0:
            raise ValueError("strike and maturity must be positive")
        nearest = min(self.nodes, key=lambda node: abs(node[0] - strike) + abs(node[1] - maturity))
        return self.nodes[nearest]


def volatility_forecast(realized_volatilities: Sequence[float], decay: float = 0.94) -> float:
    """Exponentially weighted volatility forecast."""

    if not realized_volatilities or not 0 < decay < 1:
        raise ValueError("volatility history and decay in (0,1) are required")
    weight = 1.0
    weighted_sum = 0.0
    total_weight = 0.0
    for volatility in reversed(realized_volatilities):
        if volatility < 0:
            raise ValueError("volatilities cannot be negative")
        weighted_sum += weight * volatility
        total_weight += weight
        weight *= decay
    return weighted_sum / total_weight


def gamma_exposure(contracts: Sequence[OptionContract], quantities: Sequence[int]) -> float:
    """Aggregate gamma exposure across contracts."""

    if len(contracts) != len(quantities) or not contracts:
        raise ValueError("contracts and quantities must align")
    return sum(greeks(contract).gamma * quantity * contract.spot * contract.spot for contract, quantity in zip(contracts, quantities, strict=True))


def variance_swap_fair_strike(volatilities: Sequence[float]) -> float:
    """Variance fair strike from realized vol observations."""

    if not volatilities:
        raise ValueError("volatilities cannot be empty")
    if any(vol < 0 for vol in volatilities):
        raise ValueError("volatilities cannot be negative")
    return fmean(vol * vol for vol in volatilities)


def calibrate_surface(nodes: Mapping[tuple[float, float], float], smoothing: float = 0.0) -> VolatilitySurface:
    """Create a validated surface with optional shrinkage toward mean volatility."""

    if smoothing < 0 or smoothing > 1:
        raise ValueError("smoothing must be in [0,1]")
    mean_vol = fmean(nodes.values())
    smoothed = {node: (1 - smoothing) * vol + smoothing * mean_vol for node, vol in nodes.items()}
    return VolatilitySurface(smoothed)


def _d1_d2(contract: OptionContract) -> tuple[float, float]:
    d1 = (log(contract.spot / contract.strike) + (contract.risk_free_rate + 0.5 * contract.volatility**2) * contract.time_to_expiry) / (contract.volatility * sqrt(contract.time_to_expiry))
    d2 = d1 - contract.volatility * sqrt(contract.time_to_expiry)
    return d1, d2


def _cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def _pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2 * pi)


DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class OptionMoneyness(StrEnum):
    ATM = "ATM"
    ITM = "ITM"
    OTM = "OTM"


class IVRegime(StrEnum):
    LOW_IV = "LOW_IV"
    NORMAL_IV = "NORMAL_IV"
    HIGH_IV = "HIGH_IV"


@dataclass(frozen=True)
class FNOOptionContract:
    """Exchange-traded option contract metadata for Phase 14 paper/shadow risk."""

    option_symbol: str
    strike: float
    expiry: str
    call_put: OptionType
    lot_size: int
    underlying: str
    instrument_token: int
    exchange: str
    option_type: str = "FNO_OPTION"

    def __post_init__(self) -> None:
        if not self.option_symbol.strip() or not self.underlying.strip() or not self.exchange.strip():
            raise ValueError("option symbol, underlying, and exchange are required")
        if self.strike <= 0 or self.lot_size <= 0 or self.instrument_token <= 0:
            raise ValueError("strike, lot size, and instrument token must be positive")


@dataclass(frozen=True)
class OptionChainRow:
    contract: FNOOptionContract
    last_price: float | None
    open_interest: int | None
    change_in_oi: int | None
    volume: int | None
    implied_volatility: float | None


@dataclass(frozen=True)
class OptionChainAnalytics:
    rows: tuple[dict[str, object], ...]
    atm_strike: float | str
    pcr: float | str
    data_status: str


@dataclass(frozen=True)
class OptionPosition:
    contract: FNOOptionContract
    quantity_lots: int
    spot: float | None
    implied_volatility: float | None
    risk_free_rate: float = 0.0
    days_to_expiry: int | None = None


@dataclass(frozen=True)
class PositionGreeks:
    symbol: str
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    data_status: str = "OK"


@dataclass(frozen=True)
class PortfolioGreeksReport:
    net_delta: float | str
    net_gamma: float | str
    net_theta: float | str
    net_vega: float | str
    net_rho: float | str
    position_greeks: tuple[PositionGreeks, ...]
    data_status: str
    go_live_allowed: bool = False


@dataclass(frozen=True)
class FORiskLimits:
    max_delta: float = 10_000.0
    max_gamma: float = 2_000.0
    max_theta: float = 10_000.0
    max_vega: float = 10_000.0
    max_rho: float = 10_000.0
    max_expiry_concentration: float = 0.50
    max_underlying_concentration: float = 0.50
    max_lot_exposure: int = 20


@dataclass(frozen=True)
class FORiskReport:
    greeks_report: PortfolioGreeksReport
    expiry_concentration: dict[str, float]
    underlying_concentration: dict[str, float]
    lot_exposure: int
    warnings: tuple[str, ...]
    approved: bool
    go_live_allowed: bool = False


@dataclass(frozen=True)
class IVAnalysis:
    current_iv: float | str
    iv_percentile: float | str
    iv_rank: float | str
    regime: IVRegime | str
    data_status: str


@dataclass(frozen=True)
class ExpiryRiskReport:
    days_to_expiry: int | str
    near_expiry_warning: bool
    expiry_concentration: dict[str, float]
    expiry_stress_warning: bool
    data_status: str


@dataclass(frozen=True)
class GapRiskReport:
    overnight_gap_risk: float | str
    event_gap_risk: float | str
    earnings_risk_flag: bool
    warnings: tuple[str, ...]
    data_status: str


@dataclass(frozen=True)
class OptionsRiskEvidence:
    greeks: PortfolioGreeksReport
    iv_metrics: IVAnalysis
    expiry_metrics: ExpiryRiskReport
    concentration_metrics: FORiskReport
    gap_risk: GapRiskReport
    risk_warnings: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "greeks": self.greeks,
            "iv_metrics": self.iv_metrics,
            "expiry_metrics": self.expiry_metrics,
            "concentration_metrics": self.concentration_metrics,
            "gap_risk": self.gap_risk,
            "risk_warnings": self.risk_warnings,
            "go_live_allowed": False,
        }


def classify_option_moneyness(contract: FNOOptionContract, spot: float, atm_tolerance: float = 0.005) -> OptionMoneyness:
    if spot <= 0:
        raise ValueError("spot must be positive")
    if abs(contract.strike - spot) / spot <= atm_tolerance:
        return OptionMoneyness.ATM
    if contract.call_put == OptionType.CALL:
        return OptionMoneyness.ITM if spot > contract.strike else OptionMoneyness.OTM
    return OptionMoneyness.ITM if spot < contract.strike else OptionMoneyness.OTM


def analyze_option_chain(rows: Sequence[OptionChainRow], spot: float | None) -> OptionChainAnalytics:
    if not rows or spot is None or spot <= 0:
        return OptionChainAnalytics((), DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE)
    atm = min((row.contract.strike for row in rows), key=lambda strike: abs(strike - spot))
    call_oi = sum(row.open_interest or 0 for row in rows if row.contract.call_put == OptionType.CALL)
    put_oi = sum(row.open_interest or 0 for row in rows if row.contract.call_put == OptionType.PUT)
    pcr: float | str = (put_oi / call_oi) if call_oi else DATA_UNAVAILABLE
    output = []
    for row in rows:
        missing = row.open_interest is None or row.change_in_oi is None or row.volume is None or row.implied_volatility is None
        output.append({
            "option_symbol": row.contract.option_symbol,
            "strike": row.contract.strike,
            "moneyness": classify_option_moneyness(row.contract, spot).value,
            "strike_distance": row.contract.strike - spot,
            "open_interest": row.open_interest if row.open_interest is not None else DATA_UNAVAILABLE,
            "change_in_oi": row.change_in_oi if row.change_in_oi is not None else DATA_UNAVAILABLE,
            "volume": row.volume if row.volume is not None else DATA_UNAVAILABLE,
            "iv": row.implied_volatility if row.implied_volatility is not None else DATA_UNAVAILABLE,
            "data_status": DATA_UNAVAILABLE if missing else "OK",
        })
    status = DATA_UNAVAILABLE if any(item["data_status"] == DATA_UNAVAILABLE for item in output) or pcr == DATA_UNAVAILABLE else "OK"
    return OptionChainAnalytics(tuple(output), atm, pcr, status)


def compute_position_greeks(position: OptionPosition) -> PositionGreeks | str:
    if position.spot is None or position.implied_volatility is None or position.days_to_expiry is None:
        return DATA_UNAVAILABLE
    if position.spot <= 0 or position.implied_volatility <= 0 or position.days_to_expiry <= 0:
        return DATA_UNAVAILABLE
    contract = OptionContract(position.contract.call_put, position.spot, position.contract.strike, position.days_to_expiry / 365.0, position.implied_volatility, position.risk_free_rate)
    g = greeks(contract)
    multiplier = position.quantity_lots * position.contract.lot_size
    return PositionGreeks(position.contract.option_symbol, g.delta * multiplier, g.gamma * multiplier, g.theta * multiplier, g.vega * multiplier, g.rho * multiplier)


def aggregate_portfolio_greeks(positions: Sequence[OptionPosition]) -> PortfolioGreeksReport:
    results = []
    for position in positions:
        value = compute_position_greeks(position)
        if value == DATA_UNAVAILABLE:
            return PortfolioGreeksReport(DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, tuple(results), DATA_UNAVAILABLE, False)
        results.append(value)  # type: ignore[arg-type]
    return PortfolioGreeksReport(
        sum(item.delta for item in results),
        sum(item.gamma for item in results),
        sum(item.theta for item in results),
        sum(item.vega for item in results),
        sum(item.rho for item in results),
        tuple(results),
        "OK",
        False,
    )


def assess_fo_risk(positions: Sequence[OptionPosition], limits: FORiskLimits | None = None) -> FORiskReport:
    limits = limits or FORiskLimits()
    greeks_report = aggregate_portfolio_greeks(positions)
    warnings: list[str] = []
    if greeks_report.data_status == DATA_UNAVAILABLE:
        warnings.append("Greeks DATA_UNAVAILABLE")
    else:
        checks = (
            ("delta", greeks_report.net_delta, limits.max_delta),
            ("gamma", greeks_report.net_gamma, limits.max_gamma),
            ("theta", greeks_report.net_theta, limits.max_theta),
            ("vega", greeks_report.net_vega, limits.max_vega),
            ("rho", greeks_report.net_rho, limits.max_rho),
        )
        for name, value, limit in checks:
            if abs(float(value)) > limit:
                warnings.append(f"max {name} limit breached")
    lots = sum(abs(position.quantity_lots) for position in positions)
    expiry_conc = _concentration(position.contract.expiry for position in positions)
    underlying_conc = _concentration(position.contract.underlying for position in positions)
    if lots > limits.max_lot_exposure:
        warnings.append("max lot exposure breached")
    if any(value > limits.max_expiry_concentration for value in expiry_conc.values()):
        warnings.append("max expiry concentration breached")
    if any(value > limits.max_underlying_concentration for value in underlying_conc.values()):
        warnings.append("max underlying concentration breached")
    return FORiskReport(greeks_report, expiry_conc, underlying_conc, lots, tuple(warnings), not warnings, False)


def analyze_implied_volatility(current_iv: float | None, iv_history: Sequence[float]) -> IVAnalysis:
    if current_iv is None or current_iv <= 0 or not iv_history:
        return IVAnalysis(DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE)
    clean = sorted(value for value in iv_history if value > 0)
    if not clean:
        return IVAnalysis(DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE)
    percentile = len([value for value in clean if value <= current_iv]) / len(clean) * 100.0
    iv_min = min(clean)
    iv_max = max(clean)
    rank = ((current_iv - iv_min) / (iv_max - iv_min) * 100.0) if iv_max != iv_min else 50.0
    regime = IVRegime.LOW_IV if percentile < 30 else IVRegime.HIGH_IV if percentile > 70 else IVRegime.NORMAL_IV
    return IVAnalysis(current_iv, percentile, rank, regime, "OK")


def analyze_expiry_risk(positions: Sequence[OptionPosition], near_expiry_days: int = 3) -> ExpiryRiskReport:
    if not positions or any(position.days_to_expiry is None for position in positions):
        return ExpiryRiskReport(DATA_UNAVAILABLE, False, {}, False, DATA_UNAVAILABLE)
    min_days = min(position.days_to_expiry or 0 for position in positions)
    concentration = _concentration(position.contract.expiry for position in positions)
    near = min_days <= near_expiry_days
    stress = near and any(value > 0.50 for value in concentration.values())
    return ExpiryRiskReport(min_days, near, concentration, stress, "OK")


def analyze_gap_risk(overnight_gap_pct: float | None, event_gap_pct: float | None = None, earnings_risk_flag: bool = False, warning_threshold: float = 3.0) -> GapRiskReport:
    if overnight_gap_pct is None:
        return GapRiskReport(DATA_UNAVAILABLE, DATA_UNAVAILABLE, earnings_risk_flag, ("gap data unavailable",), DATA_UNAVAILABLE)
    event_value: float | str = event_gap_pct if event_gap_pct is not None else DATA_UNAVAILABLE
    warnings: list[str] = []
    if abs(overnight_gap_pct) >= warning_threshold:
        warnings.append("overnight gap risk warning")
    if event_gap_pct is not None and abs(event_gap_pct) >= warning_threshold:
        warnings.append("event gap risk warning")
    if earnings_risk_flag:
        warnings.append("earnings risk flag")
    return GapRiskReport(overnight_gap_pct, event_value, earnings_risk_flag, tuple(warnings), "OK")


def options_risk_evidence_section(risk_report: FORiskReport, iv_analysis: IVAnalysis, expiry_report: ExpiryRiskReport, gap_report: GapRiskReport) -> dict[str, object]:
    warnings = tuple(risk_report.warnings) + tuple(gap_report.warnings)
    return {
        "greeks": risk_report.greeks_report,
        "iv_metrics": iv_analysis,
        "expiry_metrics": expiry_report,
        "concentration_metrics": risk_report,
        "gap_risk": gap_report,
        "risk_warnings": warnings,
        "go_live_allowed": False,
    }


def _concentration(values) -> dict[str, float]:
    items = tuple(values)
    total = len(items)
    if total == 0:
        return {}
    counts: dict[str, int] = {}
    for item in items:
        counts[str(item)] = counts.get(str(item), 0) + 1
    return {key: value / total for key, value in counts.items()}
