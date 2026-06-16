"""Walk-forward validation for ALPHA-GATE X."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Sequence, TypeVar

from ..market_data_spine import OHLCVCandle, BacktestResult

StrategyConfig = TypeVar("StrategyConfig")


@dataclass(frozen=True)
class WalkForwardFold(Generic[StrategyConfig]):
    """Single walk-forward train/test fold."""

    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    selected_config: StrategyConfig | None
    train_result: BacktestResult | None
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardResult(Generic[StrategyConfig]):
    """Fold-by-fold out-of-sample validation result."""

    folds: tuple[WalkForwardFold[StrategyConfig], ...]

    @property
    def aggregate_net_profit(self) -> float:
        """Return sum of fold net P&L."""

        return sum(sum(trade.pnl for trade in fold.result.trades) for fold in self.folds)


def walk_forward_splits(total_length: int, train_window: int, test_window: int) -> tuple[tuple[int, int, int, int], ...]:
    """Create rolling train/test index windows without leakage."""

    if train_window <= 0 or test_window <= 0:
        raise ValueError("train_window and test_window must be positive")
    splits = []
    start = 0
    while start + train_window + test_window <= total_length:
        train_start = start
        train_end = start + train_window
        test_start = train_end
        test_end = test_start + test_window
        splits.append((train_start, train_end, test_start, test_end))
        start += test_window
    return tuple(splits)


def run_walk_forward(
    candles: Sequence[OHLCVCandle],
    train_window: int,
    test_window: int,
    runner: Callable[[tuple[OHLCVCandle, ...]], BacktestResult],
) -> WalkForwardResult[None]:
    """Run a fixed strategy on each out-of-sample test window.

    This compatibility helper performs no optimization.  Use
    :func:`run_train_optimize_test_walk_forward` when the strategy requires
    train-window configuration selection before out-of-sample evaluation.
    """

    folds = []
    for fold_number, (train_start, train_end, test_start, test_end) in enumerate(walk_forward_splits(len(candles), train_window, test_window), start=1):
        test_candles = tuple(candles[test_start:test_end])
        folds.append(WalkForwardFold(fold_number, train_start, train_end, test_start, test_end, None, None, runner(test_candles)))
    return WalkForwardResult(tuple(folds))


def run_train_optimize_test_walk_forward(
    candles: Sequence[OHLCVCandle],
    train_window: int,
    test_window: int,
    optimizer: Callable[[tuple[OHLCVCandle, ...]], StrategyConfig],
    runner: Callable[[tuple[OHLCVCandle, ...], StrategyConfig], BacktestResult],
    train_runner: Callable[[tuple[OHLCVCandle, ...], StrategyConfig], BacktestResult] | None = None,
) -> WalkForwardResult[StrategyConfig]:
    """Run train/optimize/test walk-forward validation without leakage.

    For each fold, ``optimizer`` receives only the train-window candles and
    returns the selected strategy configuration.  The selected configuration is
    then evaluated on the out-of-sample test window.  Optional ``train_runner``
    records in-sample performance for audit evidence; it is never given the
    out-of-sample candles.
    """

    folds: list[WalkForwardFold[StrategyConfig]] = []
    for fold_number, (train_start, train_end, test_start, test_end) in enumerate(walk_forward_splits(len(candles), train_window, test_window), start=1):
        train_candles = tuple(candles[train_start:train_end])
        test_candles = tuple(candles[test_start:test_end])
        selected_config = optimizer(train_candles)
        train_result = train_runner(train_candles, selected_config) if train_runner is not None else None
        test_result = runner(test_candles, selected_config)
        folds.append(WalkForwardFold(fold_number, train_start, train_end, test_start, test_end, selected_config, train_result, test_result))
    return WalkForwardResult(tuple(folds))
