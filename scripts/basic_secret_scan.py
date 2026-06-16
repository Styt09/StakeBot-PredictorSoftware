"""Basic repository secret placeholder scan; dependency-free CI guard."""
from __future__ import annotations

import re
from pathlib import Path

PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"kite[A-Za-z0-9_\-]{20,}"),
)
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__"}


def main() -> int:
    findings: list[str] = []
    for path in Path(".").rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".toml", ".example", ""}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append(f"{path}:{line_no}")
    if findings:
        print("POTENTIAL_SECRET_FINDINGS")
        print("\n".join(findings))
        return 1
    print("NO_STATIC_SECRETS_FOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
