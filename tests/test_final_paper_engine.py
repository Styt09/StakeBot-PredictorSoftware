from pathlib import Path

from institutional_trading_platform.paper_engine import PaperEngine


def engine(tmp_path: Path) -> PaperEngine:
    return PaperEngine(tmp_path / "paper.db", starting_balance=100_000)


def test_limit_buy_uses_typed_price_and_persists(tmp_path: Path) -> None:
    first = engine(tmp_path)
    result = first.place_order(
        {
            "symbol": "NIFTY",
            "side": "BUY",
            "product": "MIS",
            "order_type": "LIMIT",
            "lots": 1,
            "lot_size": 75,
            "quantity": 75,
            "limit_price": 100,
        }
    )
    assert result["status"] == "PASS"
    assert result["paper_order"]["entry_price"] == 100
    assert result["paper_order"]["margin_reserved"] == 1500
    assert result["real_order"] is False
    assert result["go_live_allowed"] is False

    restarted = engine(tmp_path)
    status = restarted.status()
    assert len(status["open_positions"]) == 1
    assert status["open_positions"][0]["entry_price"] == 100


def test_sell_closes_long_with_correct_pnl(tmp_path: Path) -> None:
    paper = engine(tmp_path)
    opened = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "BUY",
            "product": "CNC",
            "order_type": "LIMIT",
            "quantity": 2,
            "limit_price": 100,
        }
    )
    assert opened["status"] == "PASS"

    closed = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "SELL",
            "product": "CNC",
            "order_type": "LIMIT",
            "quantity": 2,
            "limit_price": 105,
        }
    )
    assert closed["status"] == "PASS"
    assert closed["closed_trade"]["pnl"] == 10
    assert paper.status()["account_summary"]["realized_pnl"] == 10


def test_mis_short_and_buy_to_cover(tmp_path: Path) -> None:
    paper = engine(tmp_path)
    opened = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "SELL",
            "product": "MIS",
            "order_type": "LIMIT",
            "quantity": 10,
            "limit_price": 100,
        }
    )
    assert opened["status"] == "PASS"
    assert opened["paper_order"]["side"] == "SELL"

    covered = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "BUY",
            "product": "MIS",
            "order_type": "LIMIT",
            "quantity": 10,
            "limit_price": 95,
        }
    )
    assert covered["status"] == "PASS"
    assert covered["closed_trade"]["pnl"] == 50


def test_cnc_short_is_blocked(tmp_path: Path) -> None:
    paper = engine(tmp_path)
    result = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "SELL",
            "product": "CNC",
            "order_type": "LIMIT",
            "quantity": 1,
            "limit_price": 100,
        }
    )
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "CNC_SHORT_NOT_ALLOWED"


def test_market_order_fails_closed_without_quote(tmp_path: Path) -> None:
    paper = engine(tmp_path)
    result = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "BUY",
            "product": "MIS",
            "order_type": "MARKET",
            "quantity": 1,
        },
        market_price=None,
    )
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "MARKET_PRICE_UNAVAILABLE"


def test_insufficient_margin_returns_exact_reason(tmp_path: Path) -> None:
    paper = PaperEngine(tmp_path / "small.db", starting_balance=100)
    result = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "BUY",
            "product": "CNC",
            "order_type": "LIMIT",
            "quantity": 10,
            "limit_price": 100,
        }
    )
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "INSUFFICIENT_PAPER_MARGIN"
    assert result["required_margin"] == 1000


def test_mark_to_market_and_stop_for_short(tmp_path: Path) -> None:
    paper = engine(tmp_path)
    opened = paper.place_order(
        {
            "symbol": "RELIANCE",
            "side": "SELL",
            "product": "MIS",
            "order_type": "LIMIT",
            "quantity": 2,
            "limit_price": 100,
            "stop_loss": 105,
            "target_1": 95,
        }
    )
    assert opened["status"] == "PASS"
    marked = paper.mark_price("RELIANCE", 95)
    assert marked["status"] == "PASS"
    assert marked["auto_closed"][0]["exit_reason"] == "TARGET_1_HIT"
    assert marked["auto_closed"][0]["pnl"] == 10
