"""Deterministic read-only error doctor for ALPHA-GATE X.

The error doctor is intentionally non-mutating. It can diagnose and suggest safe
steps, but cannot patch files, place orders, or enable live trading.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
_LOG_PATH = Path("/tmp/alpha_gate_web.log")


ACCURACY_GATE_RULES = (
    "validated quote required",
    "validated candles required",
    "minimum 21 candles",
    "confidence >= configured minimum",
    "stop_loss required",
    "target required",
    "risk_reward >= configured minimum",
    "stale data blocked",
    "DATA_UNAVAILABLE blocked",
    "go_live_allowed:false",
)


def accuracy_gate_rules() -> dict[str, Any]:
    return {
        "status": "VALIDATED",
        "rules": list(ACCURACY_GATE_RULES),
        "minimum_confidence": _safe_float(os.environ.get("MIN_SIGNAL_CONFIDENCE"), 70.0),
        "minimum_risk_reward": _safe_float(os.environ.get("MIN_RISK_REWARD"), 1.5),
        "can_place_real_order": False,
        "go_live_allowed": False,
    }


def diagnose_local_error(
    *,
    log_path: str | Path | None = None,
    context: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source_env = env or os.environ
    path = Path(log_path) if log_path is not None else _LOG_PATH
    log_exists = path.exists()
    log_text = ""
    if log_exists:
        try:
            log_text = path.read_text(errors="replace")[-6000:]
        except Exception:
            log_text = "LOG_READ_FAILED"

    context = context or {}
    combined = "\n".join([log_text, str(_strip_sensitive(context))]).upper()

    # Configuration checks first because they are common and actionable.
    if not (source_env.get("ZERODHA_ACCESS_TOKEN") or "").strip():
        return _diagnosis(
            "ISSUE_FOUND",
            "BROKER",
            "Zerodha access token is missing; read-only quote/history calls cannot work.",
            "/api/broker/quote",
            ["ZERODHA_ACCESS_TOKEN empty"],
            ["Generate a fresh Zerodha request_token and save ZERODHA_ACCESS_TOKEN in .env."],
        )

    instrument_path = Path((source_env.get("ZERODHA_INSTRUMENT_DUMP_PATH") or "data/instruments.csv").strip() or "data/instruments.csv")
    if not instrument_path.exists() or instrument_path.stat().st_size <= 0:
        return _diagnosis(
            "ISSUE_FOUND",
            "DATA",
            "NSE instrument CSV is missing; historical candles and signal generation cannot map symbol to instrument_token.",
            "/api/market/history",
            [f"missing instrument CSV: {instrument_path}"],
            ["Download Zerodha NSE instruments and save them to data/instruments.csv."],
        )

    if not (source_env.get("OPENAI_API_KEY") or "").strip():
        return _diagnosis(
            "ISSUE_FOUND",
            "OPENAI",
            "OPENAI_API_KEY is missing; OpenAI auditor will fall back to deterministic local audit.",
            "/api/ai/health",
            ["OPENAI_API_KEY empty"],
            ["Save OPENAI_API_KEY in .env using hidden terminal input; never paste it in chat."],
        )

    if not log_exists:
        return _diagnosis(
            "NO_LOG_AVAILABLE",
            "UNKNOWN",
            "No server log found at /tmp/alpha_gate_web.log; app may still be running, but no local log evidence is available.",
            DATA_UNAVAILABLE,
            ["log file not found"],
            ["Restart the web app with stdout/stderr redirected to /tmp/alpha_gate_web.log."],
        )

    if "404" in combined or "NOT_FOUND" in combined:
        return _diagnosis("ISSUE_FOUND", "API", "A route returned 404/not_found.", DATA_UNAVAILABLE, _evidence(log_text, "404", "NOT_FOUND"), ["Check the endpoint path and rerun the matching patch script."])
    if "REFERENCEERROR" in combined or "TYPEERROR" in combined or "JS" in combined:
        return _diagnosis("ISSUE_FOUND", "UI", "Browser JavaScript appears to be failing or not updating DOM elements.", "dashboard", _evidence(log_text, "ReferenceError", "TypeError", "JS"), ["Load with a cache-busting URL and verify emergency UI script is present."])
    if "TOKENEXCEPTION" in combined or "TOKEN_EXPIRED" in combined or "TOKEN" in combined and "EXPIRED" in combined:
        return _diagnosis("ISSUE_FOUND", "BROKER", "Zerodha token appears expired or invalid.", "/api/broker/quote", _evidence(log_text, "TokenException", "expired"), ["Generate a fresh Zerodha request_token and update ZERODHA_ACCESS_TOKEN."])
    if "ZERODHA_QUOTE" in combined and ("UNAVAILABLE" in combined or "ERROR" in combined):
        return _diagnosis("ISSUE_FOUND", "BROKER", "Zerodha quote endpoint is unavailable.", "/api/broker/quote", _evidence(log_text, "ZERODHA_QUOTE", "UNAVAILABLE"), ["Verify access token, API key, market hours, and Kite Connect package."])
    if "INSTRUMENT_CSV_UNAVAILABLE" in combined or "INSTRUMENT_TOKEN_NOT_FOUND" in combined:
        return _diagnosis("ISSUE_FOUND", "DATA", "Instrument lookup failed; historical candles unavailable.", "/api/market/history", _evidence(log_text, "INSTRUMENT"), ["Refresh data/instruments.csv from Zerodha instruments('NSE')."])
    if "INSUFFICIENT_CANDLES" in combined:
        return _diagnosis("ISSUE_FOUND", "SIGNAL", "Signal engine has fewer candles than the minimum requirement.", "/api/signal/live", _evidence(log_text, "INSUFFICIENT_CANDLES"), ["Wait for more candle data or request a supported historical interval."])
    if "DATA_UNAVAILABLE" in combined:
        return _diagnosis("ISSUE_FOUND", "DATA", "One or more required data fields are DATA_UNAVAILABLE.", DATA_UNAVAILABLE, _evidence(log_text, "DATA_UNAVAILABLE"), ["Trace the first upstream endpoint returning DATA_UNAVAILABLE and fix data source before signal generation."])
    if "PAPER" in combined and "BLOCKED" in combined:
        return _diagnosis("ISSUE_FOUND", "PAPER", "Paper order or paper auto-trade was blocked by safety rules.", "/api/paper/order", _evidence(log_text, "PAPER", "BLOCKED"), ["Inspect blocked_reasons and do not bypass risk checks."])
    if "BROKER_MUTATION_DISABLED" in combined:
        return _diagnosis("PASS", "BROKER", "Broker mutation was blocked as designed.", "/api/broker/order/place", ["BROKER_MUTATION_DISABLED"], ["No action required; real orders remain fail-closed."])

    return _diagnosis("PASS", "UNKNOWN", "No known blocking error pattern found in local evidence.", DATA_UNAVAILABLE, ["log inspected"], ["Use /api/ai/diagnose with current error context for a more specific review."])


def latest_error_report(context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    diagnosis = diagnose_local_error(context=context)
    return {
        "status": diagnosis["status"],
        "diagnosis": diagnosis,
        "accuracy_gates": accuracy_gate_rules(),
        "safe_to_auto_patch": False,
        "requires_human_approval": True,
        "can_place_real_order": False,
        "go_live_allowed": False,
    }


def _diagnosis(status: str, category: str, root_cause: str, endpoint: str, evidence: list[str], suggestions: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "category": category,
        "root_cause": root_cause,
        "affected_endpoint": endpoint,
        "evidence": list(evidence),
        "safe_fix_suggestions": list(suggestions),
        "safe_to_auto_patch": False,
        "requires_human_approval": True,
        "can_place_real_order": False,
        "go_live_allowed": False,
    }


def _evidence(text: str, *needles: str) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()
    found: list[str] = []
    upper_needles = [needle.upper() for needle in needles]
    for line in lines[-80:]:
        upper = line.upper()
        if any(needle in upper for needle in upper_needles):
            found.append(_mask_line(line)[-400:])
        if len(found) >= 10:
            break
    return found


def _mask_line(line: str) -> str:
    result = line
    for token in ("access_token", "request_token", "api_secret", "api_key", "OPENAI_API_KEY", "ZERODHA_ACCESS_TOKEN"):
        if token.lower() in result.lower():
            result = result.replace(token, f"{token}=SET-HIDDEN")
    return result


def _strip_sensitive(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        clean: dict[str, Any] = {}
        for key, value in payload.items():
            upper = str(key).upper()
            if any(secret in upper for secret in ("TOKEN", "SECRET", "API_KEY", "PASSWORD", "AUTHORIZATION")):
                clean[str(key)] = "SET-HIDDEN" if value else "EMPTY"
            else:
                clean[str(key)] = _strip_sensitive(value)
        return clean
    if isinstance(payload, (list, tuple)):
        return [_strip_sensitive(item) for item in payload[:50]]
    return payload


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
