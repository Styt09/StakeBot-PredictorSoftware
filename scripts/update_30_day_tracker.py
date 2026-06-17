#!/usr/bin/env python3
"""Update the local 30-day shadow validation tracker from saved evidence folders.

This script is intentionally local-only: it reads shadow_evidence/YYYY-MM-DD
folders and writes shadow_evidence/30_day_tracker.md. The shadow_evidence folder
is ignored by git so private runtime evidence is not accidentally committed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path.cwd()
EVIDENCE_ROOT = ROOT / "shadow_evidence"
TRACKER_PATH = EVIDENCE_ROOT / "30_day_tracker.md"
MAX_DAYS = 30


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ok_file(day_dir: Path, filename: str) -> str:
    path = day_dir / filename
    if not path.exists() or path.stat().st_size <= 0:
        return "NO"
    data = _load_json(path)
    status = str(data.get("status", "")).upper()
    if status in {"DATA_UNAVAILABLE", "ERROR", "FAILED"}:
        return "CHECK"
    return "YES"


def _note_for_day(day_dir: Path) -> str:
    live_block = _load_json(day_dir / "live_order_block_check.json")
    readiness = _load_json(day_dir / "readiness_gates.json")
    notes: list[str] = []

    if live_block:
        text = json.dumps(live_block).upper()
        if "BLOCK" in text and "BROKER_ORDER_ID" in text:
            notes.append("live blocked")
        elif "BLOCK" in text:
            notes.append("live block checked")
        else:
            notes.append("check live block")

    if readiness:
        if readiness.get("go_live_allowed") is False:
            notes.append("go_live=false")
        live_ready = readiness.get("live_ready")
        if live_ready is False:
            notes.append("live NO-GO")

    if not notes:
        notes.append("review evidence")
    return "; ".join(notes)


def main() -> None:
    EVIDENCE_ROOT.mkdir(exist_ok=True)
    day_dirs = sorted(
        [p for p in EVIDENCE_ROOT.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"],
        key=lambda p: p.name,
    )[:MAX_DAYS]

    rows = []
    for idx in range(1, MAX_DAYS + 1):
        if idx <= len(day_dirs):
            d = day_dirs[idx - 1]
            rows.append(
                f"| {idx} | {d.name} | {_ok_file(d, 'manifest.json')} | {_ok_file(d, 'broker_health.json')} | {_ok_file(d, 'readiness_report.json')} | {_ok_file(d, 'shadow_report.json')} | {_note_for_day(d)} |"
            )
        else:
            rows.append(f"| {idx} | | | | | | |")

    content = "\n".join(
        [
            "# 30-Day Shadow Validation Tracker",
            "",
            "Verdict during validation:",
            "- PAPER: READY CANDIDATE",
            "- SHADOW: READY CANDIDATE",
            "- LIVE: NO-GO",
            "- go_live_allowed=false",
            "",
            "| Day | Date | Evidence Saved | Broker Health | Readiness Report | Shadow Report | Notes |",
            "|---|---|---|---|---|---|---|",
            *rows,
            "",
        ]
    )
    TRACKER_PATH.write_text(content, encoding="utf-8")
    print(f"✅ Tracker updated: {TRACKER_PATH}")
    print(TRACKER_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
