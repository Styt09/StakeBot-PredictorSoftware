"""Static safety scan that fails if forbidden real-order calls are present."""
from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    ".place_order(",
    "kite.place_order",
    "place_order(variety",
    "place_order(tradingsymbol",
)
ALLOWED_FILES = {
    "scripts/no_live_order_static_scan.py",
    "src/institutional_trading_platform/paper_trading/paper_broker.py",
    "tests/test_alpha_gate_x.py",
    "tests/test_critical_hardening.py",
}
ALLOWED_SNIPPETS = (
    "self.paper_broker.place_order",
    "broker.place_order",
    "def place_order",
    "live_broker.place_order is impossible",
    "called = False",
)


def main() -> int:
    violations: list[str] = []
    roots = [Path("src"), Path("scripts")]
    for root in roots:
        for path in root.rglob("*.py"):
            rel = path.as_posix()
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), 1):
                if any(token in line for token in FORBIDDEN) and not any(snippet in line for snippet in ALLOWED_SNIPPETS):
                    if rel not in ALLOWED_FILES:
                        violations.append(f"{rel}:{line_no}:{line.strip()}")
    if violations:
        print("FORBIDDEN_REAL_ORDER_PATHS_FOUND")
        print("\n".join(violations))
        return 1
    print("NO_LIVE_ORDER_PATHS_FOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
