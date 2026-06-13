"""Portfolio construction and capital allocation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PositionSizingRequest:
    """Inputs for volatility-targeted, risk-budget-aware position sizing."""

    capital: float
    entry_price: float
    stop_loss: float
    risk_budget_fraction: float
    volatility: float
    target_volatility: float
    max_position_fraction: float = 1.0

    def __post_init__(self) -> None:
        for field_name in ("capital", "entry_price", "stop_loss", "risk_budget_fraction", "target_volatility", "max_position_fraction"):
            value = getattr(self, field_name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be positive and finite")
        if not isfinite(self.volatility) or self.volatility < 0:
            raise ValueError("volatility must be non-negative and finite")
        if self.entry_price == self.stop_loss:
            raise ValueError("entry_price and stop_loss must differ")
        if self.risk_budget_fraction > 1.0 or self.max_position_fraction > 1.0:
            raise ValueError("risk and max position fractions must be <= 1")


@dataclass(frozen=True)
class PositionSizingResult:
    """Validated position sizing output."""

    quantity: int
    notional: float
    capital_fraction: float
    risk_amount: float


def volatility_targeted_position_size(request: PositionSizingRequest) -> PositionSizingResult:
    """Compute a conservative integer quantity constrained by risk and volatility."""

    risk_per_unit = abs(request.entry_price - request.stop_loss)
    risk_budget = request.capital * request.risk_budget_fraction
    risk_quantity = int(risk_budget / risk_per_unit)
    volatility_scale = 1.0 if request.volatility == 0 else min(1.0, request.target_volatility / request.volatility)
    max_notional = request.capital * request.max_position_fraction * volatility_scale
    notional_quantity = int(max_notional / request.entry_price)
    quantity = max(0, min(risk_quantity, notional_quantity))
    notional = quantity * request.entry_price
    return PositionSizingResult(
        quantity=quantity,
        notional=notional,
        capital_fraction=notional / request.capital,
        risk_amount=quantity * risk_per_unit,
    )


def inverse_volatility_weights(volatilities: Mapping[str, float]) -> dict[str, float]:
    """Return long-only inverse-volatility weights that sum to one."""

    if not volatilities:
        raise ValueError("volatilities cannot be empty")
    inverse_values: dict[str, float] = {}
    for asset, volatility in volatilities.items():
        if not asset.strip():
            raise ValueError("asset names cannot be blank")
        if not isfinite(volatility) or volatility <= 0:
            raise ValueError("volatilities must be positive and finite")
        inverse_values[asset] = 1.0 / volatility
    total = sum(inverse_values.values())
    return {asset: value / total for asset, value in inverse_values.items()}


def equal_risk_contribution_weights(volatilities: Mapping[str, float]) -> dict[str, float]:
    """Alias for diagonal risk-parity weights under zero-correlation assumption."""

    return inverse_volatility_weights(volatilities)


def portfolio_expected_return(weights: Mapping[str, float], expected_returns: Mapping[str, float]) -> float:
    """Compute expected portfolio return after validating coverage."""

    _validate_weights(weights)
    missing = [asset for asset in weights if asset not in expected_returns]
    if missing:
        raise ValueError(f"missing expected returns for: {', '.join(missing)}")
    return sum(weights[asset] * expected_returns[asset] for asset in weights)


def rebalance_trades(current_weights: Mapping[str, float], target_weights: Mapping[str, float], portfolio_value: float) -> dict[str, float]:
    """Compute notional trade list needed to move from current to target weights."""

    _validate_weights(target_weights)
    if not isfinite(portfolio_value) or portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive and finite")
    assets = set(current_weights) | set(target_weights)
    trades = {}
    for asset in sorted(assets):
        current = current_weights.get(asset, 0.0)
        target = target_weights.get(asset, 0.0)
        if current < 0:
            raise ValueError("current weights cannot be negative")
        trades[asset] = (target - current) * portfolio_value
    return trades


def realized_correlation(series_a: Sequence[float], series_b: Sequence[float]) -> float:
    """Compute sample correlation for cross-asset intelligence."""

    if len(series_a) != len(series_b) or len(series_a) < 2:
        raise ValueError("series must have the same length of at least two")
    mean_a = fmean(series_a)
    mean_b = fmean(series_b)
    covariance = sum((a - mean_a) * (b - mean_b) for a, b in zip(series_a, series_b, strict=True))
    variance_a = sum((a - mean_a) ** 2 for a in series_a)
    variance_b = sum((b - mean_b) ** 2 for b in series_b)
    if variance_a == 0 or variance_b == 0:
        return 0.0
    return covariance / (variance_a * variance_b) ** 0.5


def _validate_weights(weights: Mapping[str, float]) -> None:
    if not weights:
        raise ValueError("weights cannot be empty")
    total = 0.0
    for asset, weight in weights.items():
        if not asset.strip():
            raise ValueError("asset names cannot be blank")
        if not isfinite(weight) or weight < 0:
            raise ValueError("weights must be non-negative and finite")
        total += weight
    if abs(total - 1.0) > 1e-6:
        raise ValueError("weights must sum to one")


def mean_variance_weights(expected_returns: Mapping[str, float], variances: Mapping[str, float], risk_aversion: float = 1.0) -> dict[str, float]:
    """Long-only diagonal mean-variance optimizer."""

    if risk_aversion <= 0:
        raise ValueError("risk_aversion must be positive")
    raw = {}
    for asset, expected_return in expected_returns.items():
        variance = variances.get(asset)
        if variance is None or variance <= 0:
            raise ValueError("each asset requires positive variance")
        raw[asset] = max(0.0, expected_return / (risk_aversion * variance))
    if sum(raw.values()) == 0:
        return {asset: 1.0 / len(raw) for asset in raw}
    total = sum(raw.values())
    return {asset: value / total for asset, value in raw.items()}


def hierarchical_risk_parity_weights(cluster_volatilities: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    """Two-level HRP approximation: allocate across clusters then within clusters by inverse volatility."""

    if not cluster_volatilities:
        raise ValueError("cluster_volatilities cannot be empty")
    cluster_risk = {cluster: fmean(vols.values()) for cluster, vols in cluster_volatilities.items() if vols}
    cluster_weights = inverse_volatility_weights(cluster_risk)
    result = {}
    for cluster, vols in cluster_volatilities.items():
        within = inverse_volatility_weights(vols)
        for asset, weight in within.items():
            result[asset] = cluster_weights[cluster] * weight
    return result


def black_litterman_weights(market_weights: Mapping[str, float], views: Mapping[str, float], confidence: float = 0.5) -> dict[str, float]:
    """Blend market equilibrium weights with normalized investor views."""

    _validate_weights(market_weights)
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be in [0,1]")
    view_assets = {asset: max(0.0, view) for asset, view in views.items() if asset in market_weights}
    if not view_assets or sum(view_assets.values()) == 0:
        return dict(market_weights)
    total_view = sum(view_assets.values())
    normalized_views = {asset: value / total_view for asset, value in view_assets.items()}
    blended = {}
    for asset, market_weight in market_weights.items():
        blended[asset] = (1 - confidence) * market_weight + confidence * normalized_views.get(asset, 0.0)
    total = sum(blended.values())
    return {asset: value / total for asset, value in blended.items()}


def cvar_optimization_weights(cvars: Mapping[str, float]) -> dict[str, float]:
    """Long-only allocation inversely proportional to asset CVaR."""

    return inverse_volatility_weights(cvars)


def robust_optimization_weights(candidate_weights: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Robust allocation as the average of valid candidate allocations."""

    if not candidate_weights:
        raise ValueError("candidate_weights cannot be empty")
    for weights in candidate_weights:
        _validate_weights(weights)
    assets = sorted(set().union(*(weights.keys() for weights in candidate_weights)))
    averaged = {asset: fmean(weights.get(asset, 0.0) for weights in candidate_weights) for asset in assets}
    total = sum(averaged.values())
    return {asset: value / total for asset, value in averaged.items()}


def capacity_constrained_allocation(target_weights: Mapping[str, float], capacities: Mapping[str, float], portfolio_value: float) -> dict[str, float]:
    """Scale target weights down when notional capacity constraints bind."""

    _validate_weights(target_weights)
    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive")
    adjusted = {}
    for asset, weight in target_weights.items():
        capacity = capacities.get(asset, portfolio_value)
        if capacity < 0:
            raise ValueError("capacities cannot be negative")
        adjusted[asset] = min(weight, capacity / portfolio_value)
    total = sum(adjusted.values())
    if total == 0:
        raise ValueError("all capacities are zero")
    return {asset: value / total for asset, value in adjusted.items()}


@dataclass(frozen=True)
class PortfolioPosition:
    """Current portfolio exposure used by Phase 12 portfolio controls."""

    symbol: str
    sector: str
    quantity: int
    price: float
    volatility: float

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class PortfolioSignalAllocation:
    """Candidate signal allocation before portfolio-level risk clipping."""

    symbol: str
    sector: str
    side: str
    confidence: float
    expected_return: float
    volatility: float
    entry_price: float
    stop_loss: float
    win_probability: float = 0.5
    reward_risk: float = 1.0
    timeframe: str = "5m"


@dataclass(frozen=True)
class PortfolioRiskLimits:
    """Institutional portfolio constraints; defaults are conservative."""

    max_symbol_weight: float = 0.20
    max_sector_weight: float = 0.35
    max_correlation: float = 0.80
    target_portfolio_volatility: float = 0.12
    max_portfolio_var_pct: float = 5.0
    max_portfolio_cvar_pct: float = 8.0
    max_drawdown_pct: float = 15.0
    max_gross_exposure: float = 1.0
    max_kelly_fraction: float = 0.25
    risk_per_trade_fraction: float = 0.005

    def __post_init__(self) -> None:
        for field_name in (
            "max_symbol_weight",
            "max_sector_weight",
            "target_portfolio_volatility",
            "max_portfolio_var_pct",
            "max_portfolio_cvar_pct",
            "max_drawdown_pct",
            "max_gross_exposure",
            "max_kelly_fraction",
            "risk_per_trade_fraction",
        ):
            value = getattr(self, field_name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be positive and finite")
        if not 0 <= self.max_correlation <= 1:
            raise ValueError("max_correlation must be in [0,1]")
        if self.max_symbol_weight > 1 or self.max_sector_weight > 1 or self.max_gross_exposure > 2:
            raise ValueError("portfolio exposure limits are outside conservative bounds")


@dataclass(frozen=True)
class PortfolioAllocation:
    """Approved paper/shadow allocation after portfolio controls."""

    symbol: str
    sector: str
    weight: float
    quantity: int
    notional: float
    risk_amount: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioRiskReport:
    """Portfolio-level risk diagnostics used before approval/manual review."""

    gross_exposure: float
    sector_exposures: dict[str, float]
    symbol_exposures: dict[str, float]
    portfolio_volatility: float
    portfolio_var_pct: float
    portfolio_cvar_pct: float
    drawdown_pct: float
    concentration_warnings: tuple[str, ...]
    correlation_warnings: tuple[str, ...]
    approved: bool
    reasons: tuple[str, ...]
    go_live_allowed: bool = False


@dataclass(frozen=True)
class PortfolioConstructionResult:
    """Final Phase 12 portfolio construction result."""

    allocations: tuple[PortfolioAllocation, ...]
    target_weights: dict[str, float]
    risk_report: PortfolioRiskReport
    rejected_symbols: dict[str, tuple[str, ...]]
    recommendation: str
    go_live_allowed: bool = False


class PortfolioConstructionEngine:
    """Build risk-capped paper/shadow allocations from ALPHA-GATE X signals."""

    def __init__(self, limits: PortfolioRiskLimits | None = None) -> None:
        self.limits = limits or PortfolioRiskLimits()

    def construct(
        self,
        *,
        capital: float,
        candidates: Sequence[PortfolioSignalAllocation],
        current_positions: Sequence[PortfolioPosition] = (),
        correlations: Mapping[tuple[str, str], float] | None = None,
        equity_curve: Sequence[float] = (),
        historical_returns: Mapping[str, Sequence[float]] | None = None,
    ) -> PortfolioConstructionResult:
        if not isfinite(capital) or capital <= 0:
            raise ValueError("capital must be positive and finite")
        correlations = correlations or {}
        historical_returns = historical_returns or {}
        rejected: dict[str, tuple[str, ...]] = {}
        accepted = []
        for candidate in candidates:
            reasons = self._candidate_rejections(candidate, accepted, current_positions, correlations)
            if reasons:
                rejected[candidate.symbol] = reasons
            else:
                accepted.append(candidate)
        if not accepted:
            report = self._risk_report({}, current_positions, capital, historical_returns, equity_curve, ("no candidates passed portfolio constraints",), correlations)
            return PortfolioConstructionResult((), {}, report, rejected, "CONTINUE_PAPER", False)

        base_weights = self._base_weights(accepted)
        clipped = self._apply_symbol_and_sector_caps(base_weights, {item.symbol: item.sector for item in accepted})
        allocations = tuple(self._allocation(capital, candidate, clipped[candidate.symbol]) for candidate in accepted if clipped.get(candidate.symbol, 0.0) > 0)
        target_weights = {allocation.symbol: allocation.weight for allocation in allocations}
        report = self._risk_report(target_weights, current_positions, capital, historical_returns, equity_curve, (), correlations)
        recommendation = "PORTFOLIO_APPROVED" if report.approved and allocations else "PORTFOLIO_BLOCKED"
        return PortfolioConstructionResult(allocations, target_weights, report, rejected, recommendation, False)

    def _candidate_rejections(
        self,
        candidate: PortfolioSignalAllocation,
        accepted: Sequence[PortfolioSignalAllocation],
        current_positions: Sequence[PortfolioPosition],
        correlations: Mapping[tuple[str, str], float],
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if candidate.entry_price <= 0 or candidate.stop_loss <= 0 or candidate.entry_price == candidate.stop_loss:
            reasons.append("invalid entry/stop")
        if candidate.volatility <= 0:
            reasons.append("missing positive volatility")
        if not 0 <= candidate.confidence <= 1:
            reasons.append("confidence outside [0,1]")
        if kelly_fraction(candidate.win_probability, candidate.reward_risk, self.limits.max_kelly_fraction) <= 0:
            reasons.append("kelly fraction is zero")
        for other in tuple(accepted) + tuple(PortfolioSignalAllocation(p.symbol, p.sector, "HOLD", 1.0, 0.0, p.volatility, p.price, max(p.price * 0.99, 0.01)) for p in current_positions):
            corr = _correlation_lookup(correlations, candidate.symbol, other.symbol)
            if corr is not None and corr > self.limits.max_correlation:
                reasons.append(f"correlation limit breached with {other.symbol}")
        return tuple(reasons)

    def _base_weights(self, candidates: Sequence[PortfolioSignalAllocation]) -> dict[str, float]:
        raw = {}
        for candidate in candidates:
            vol_scale = self.limits.target_portfolio_volatility / candidate.volatility
            edge = max(candidate.expected_return, 0.0) * max(candidate.confidence, 0.0)
            kelly = kelly_fraction(candidate.win_probability, candidate.reward_risk, self.limits.max_kelly_fraction)
            raw[candidate.symbol] = max(0.0, edge * vol_scale * kelly)
        if sum(raw.values()) == 0:
            raw = {candidate.symbol: 1.0 / candidate.volatility for candidate in candidates}
        total = sum(raw.values())
        return {symbol: value / total for symbol, value in raw.items()}

    def _apply_symbol_and_sector_caps(self, weights: Mapping[str, float], sectors: Mapping[str, str]) -> dict[str, float]:
        clipped = {symbol: min(weight, self.limits.max_symbol_weight) for symbol, weight in weights.items()}
        sector_totals: dict[str, float] = {}
        for symbol, weight in clipped.items():
            sector_totals[sectors[symbol]] = sector_totals.get(sectors[symbol], 0.0) + weight
        for sector, total in sector_totals.items():
            if total > self.limits.max_sector_weight:
                scale = self.limits.max_sector_weight / total
                for symbol, symbol_sector in sectors.items():
                    if symbol_sector == sector:
                        clipped[symbol] *= scale
        gross = sum(clipped.values())
        if gross > self.limits.max_gross_exposure:
            clipped = {symbol: weight / gross * self.limits.max_gross_exposure for symbol, weight in clipped.items()}
            gross = sum(clipped.values())
        return {symbol: (weight / gross if gross else 0.0) for symbol, weight in clipped.items()}

    def _allocation(self, capital: float, candidate: PortfolioSignalAllocation, weight: float) -> PortfolioAllocation:
        max_notional_qty = int((capital * weight) / candidate.entry_price)
        risk_per_share = abs(candidate.entry_price - candidate.stop_loss)
        risk_qty = int((capital * self.limits.risk_per_trade_fraction) / risk_per_share) if risk_per_share else 0
        quantity = max(0, min(max_notional_qty, risk_qty))
        notional = quantity * candidate.entry_price
        actual_weight = notional / capital if capital else 0.0
        return PortfolioAllocation(candidate.symbol, candidate.sector, actual_weight, quantity, notional, quantity * risk_per_share, ("portfolio sized",))

    def _risk_report(
        self,
        target_weights: Mapping[str, float],
        current_positions: Sequence[PortfolioPosition],
        capital: float,
        historical_returns: Mapping[str, Sequence[float]],
        equity_curve: Sequence[float],
        base_reasons: Sequence[str],
        correlations: Mapping[tuple[str, str], float],
    ) -> PortfolioRiskReport:
        symbol_exposures = dict(target_weights)
        for position in current_positions:
            symbol_exposures[position.symbol] = symbol_exposures.get(position.symbol, 0.0) + max(position.notional, 0.0) / capital
        sector_exposures: dict[str, float] = {}
        # Known sectors from current positions are always included. Target sector checks are handled pre-allocation.
        for position in current_positions:
            sector_exposures[position.sector] = sector_exposures.get(position.sector, 0.0) + max(position.notional, 0.0) / capital
        gross = sum(abs(weight) for weight in symbol_exposures.values())
        port_vol = portfolio_volatility(symbol_exposures, {symbol: _series_volatility(values) for symbol, values in historical_returns.items()}, correlations)
        var_pct, cvar_pct = portfolio_var_cvar_pct(symbol_exposures, historical_returns)
        drawdown_pct = _drawdown_pct(equity_curve)
        concentration_warnings = []
        correlation_warnings = []
        reasons = list(base_reasons)
        for symbol, weight in symbol_exposures.items():
            if weight > self.limits.max_symbol_weight:
                concentration_warnings.append(f"{symbol} exceeds symbol cap")
        for sector, weight in sector_exposures.items():
            if weight > self.limits.max_sector_weight:
                concentration_warnings.append(f"{sector} exceeds sector cap")
        for (left, right), corr in correlations.items():
            if left in symbol_exposures and right in symbol_exposures and corr > self.limits.max_correlation:
                correlation_warnings.append(f"{left}/{right} correlation {corr:.2f} exceeds cap")
        if gross > self.limits.max_gross_exposure:
            reasons.append("gross exposure limit breached")
        if var_pct > self.limits.max_portfolio_var_pct:
            reasons.append("portfolio VaR limit breached")
        if cvar_pct > self.limits.max_portfolio_cvar_pct:
            reasons.append("portfolio CVaR limit breached")
        if drawdown_pct > self.limits.max_drawdown_pct:
            reasons.append("portfolio drawdown limit breached")
        reasons.extend(concentration_warnings)
        reasons.extend(correlation_warnings)
        return PortfolioRiskReport(gross, sector_exposures, symbol_exposures, port_vol, var_pct, cvar_pct, drawdown_pct, tuple(concentration_warnings), tuple(correlation_warnings), not reasons, tuple(reasons), False)


def kelly_fraction(win_probability: float, reward_risk: float, cap: float = 0.25) -> float:
    """Return capped fractional Kelly sizing; never leverages beyond cap."""

    if not 0 <= win_probability <= 1:
        raise ValueError("win_probability must be in [0,1]")
    if reward_risk <= 0 or cap <= 0:
        raise ValueError("reward_risk and cap must be positive")
    raw = win_probability - ((1.0 - win_probability) / reward_risk)
    return max(0.0, min(raw, cap))


def portfolio_volatility(weights: Mapping[str, float], volatilities: Mapping[str, float], correlations: Mapping[tuple[str, str], float] | None = None) -> float:
    """Compute portfolio volatility from weights, vols, and pairwise correlations."""

    correlations = correlations or {}
    variance = 0.0
    for left, left_weight in weights.items():
        left_vol = volatilities.get(left, 0.0)
        variance += (left_weight * left_vol) ** 2
        for right, right_weight in weights.items():
            if right <= left:
                continue
            right_vol = volatilities.get(right, 0.0)
            corr = _correlation_lookup(correlations, left, right)
            variance += 2 * left_weight * right_weight * left_vol * right_vol * (corr if corr is not None else 0.0)
    return max(variance, 0.0) ** 0.5


def portfolio_var_cvar_pct(weights: Mapping[str, float], returns: Mapping[str, Sequence[float]], confidence: float = 0.95) -> tuple[float, float]:
    """Historical VaR/CVaR percentage using supplied return observations."""

    if not returns or not weights:
        return 0.0, 0.0
    length = min((len(values) for values in returns.values() if values), default=0)
    if length == 0:
        return 0.0, 0.0
    portfolio_returns = []
    for index in range(length):
        portfolio_returns.append(sum(weights.get(symbol, 0.0) * returns.get(symbol, ())[index] for symbol in weights if len(returns.get(symbol, ())) > index))
    losses = sorted([-value * 100.0 for value in portfolio_returns])
    if not losses:
        return 0.0, 0.0
    var_index = max(0, min(len(losses) - 1, int(confidence * len(losses)) - 1))
    var = max(0.0, losses[var_index])
    tail = [loss for loss in losses[var_index:] if loss >= var]
    cvar = fmean(tail) if tail else var
    return var, cvar


def _series_volatility(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = fmean(values)
    variance = fmean((value - avg) ** 2 for value in values)
    return variance ** 0.5


def _correlation_lookup(correlations: Mapping[tuple[str, str], float], left: str, right: str) -> float | None:
    return correlations.get((left, right), correlations.get((right, left)))


def _drawdown_pct(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        max_dd = max(max_dd, ((peak - equity) / peak * 100.0) if peak else 0.0)
    return max_dd
