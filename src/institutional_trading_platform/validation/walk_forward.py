"""Walk-forward validation for ALPHA-GATE X."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ..market_data_spine import OHLCVCandle, BacktestResult


@dataclass(frozen=True)
class WalkForwardFold:
    """Single walk-forward train/test fold."""

    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardResult:
    """Fold-by-fold out-of-sample validation result."""

    folds: tuple[WalkForwardFold, ...]

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
) -> WalkForwardResult:
    """Run strategy only on each out-of-sample test window."""

    folds = []
    for fold_number, (train_start, train_end, test_start, test_end) in enumerate(walk_forward_splits(len(candles), train_window, test_window), start=1):
        del train_start, train_end  # Training data is intentionally not optimized in this foundation.
        test_candles = tuple(candles[test_start:test_end])
        folds.append(WalkForwardFold(fold_number, test_start - train_window, test_start, test_start, test_end, runner(test_candles)))
    return WalkForwardResult(tuple(folds))
