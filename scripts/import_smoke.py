"""Import smoke test for the public package without requiring editable install."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import institutional_trading_platform as itp

print({"imported": True, "package": itp.__name__})
