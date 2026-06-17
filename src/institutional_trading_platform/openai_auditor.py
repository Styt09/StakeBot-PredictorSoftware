"""Read-only OpenAI auditor for ALPHA-GATE X.

This module is intentionally fail-closed:
- It never places broker orders.
- It never enables live trading.
- It never exposes secrets.
- OpenAI may only explain or downgrade risk; deterministic local gates remain authoritative.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
_ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD", "NO_TRADE", DATA_UNAVAILABLE}
_ALLOWED_STATUS = {"PASS", "BLOCKED", "OPENAI_UNAVAILABLE", "AI_AUDITOR_UNAVAILABLE"}
_ALLOWED_GRADES = {"A", "B", "C", "D", "F", DATA_UNAVAILABLE}


@dataclass(frozen=True)
class OpenAIAuditorConfig:
    """Backend-only OpenAI auditor configuration."""

    api_key: str = ""
    model: str = "gpt-5.1-mini"
    auditor_enabled: bool = True
    autofix_enabled: bool = False
    can_modify_files: bool = False
    can_place_orders: bool = False
    go_live_allowed: bool = False
    timeout_seconds: float = 12.0


@dataclass(frozen=True)
class OpenAIAuditResult:
    """Safe normalized audit response."""

    status: str
    auditor: str
    original_action: str
    final_action: str
    confidence_grade: str
    blocked_reasons: tuple[str, ...]
    accuracy_notes: tuple[str, ...]
    safe_fix_suggestions: tuple[str, ...]
    requires_human_review: bool = True
    can_place_real_order: bool = False
    go_live_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blocked_reasons"] = list(self.blocked_reasons)
        payload["accuracy_notes"] = list(self.accuracy_notes)
        payload["safe_fix_suggestions"] = list(self.safe_fix_suggestions)
        return payload


class OpenAIReadOnlyAuditor:
    """Read-only OpenAI adapter with deterministic local gates."""

    def __init__(
        self,
        config: OpenAIAuditorConfig | None = None,
        *,
        transport: Callable[[dict[str, Any], OpenAIAuditorConfig], Mapping[str, Any] | str] | None = None,
    ) -> None:
        self.config = config or get_openai_auditor_config()
        self._transport = transport

    def health(self) -> dict[str, Any]:
        if not self.config.auditor_enabled:
            status = "DISABLED"
        elif not self.config.api_key:
            status = "OPENAI_KEY_MISSING"
        else:
            status = "READY"
        return {
            "status": status,
            "model": self.config.model,
            "auditor_enabled": self.config.auditor_enabled,
            "autofix_enabled": False,
            "can_modify_files": False,
            "can_place_orders": False,
            "api_key": mask_openai_key(self.config.api_key),
            "go_live_allowed": False,
        }

    def audit_signal(
        self,
        *,
        symbol: str,
        signal: Mapping[str, Any] | None,
        market_quote: Mapping[str, Any] | None,
        market_history: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        local = deterministic_signal_audit(
            symbol=symbol,
            signal=signal or {},
            market_quote=market_quote or {},
            market_history=market_history or {},
        )

        # Deterministic safety gates are authoritative. Missing/weak data does not need an LLM.
        if local["status"] == "BLOCKED":
            if not self.config.api_key or not self.config.auditor_enabled:
                local["status"] = "OPENAI_UNAVAILABLE" if not self.config.api_key else "BLOCKED"
            return _force_safe_audit(local, original_signal=signal or {})

        if not self.config.auditor_enabled:
            return _force_safe_audit(local, original_signal=signal or {})
        if not self.config.api_key:
            local["status"] = "OPENAI_UNAVAILABLE"
            local["accuracy_notes"].append("OpenAI key missing; deterministic local audit used.")
            return _force_safe_audit(local, original_signal=signal or {})

        prompt = _audit_prompt(symbol=symbol, signal=signal or {}, market_quote=market_quote or {}, market_history=market_history or {})
        try:
            ai_payload = self._call_openai_json(prompt)
            merged = _merge_ai_with_local(ai_payload, local, signal or {})
            return _force_safe_audit(merged, original_signal=signal or {})
        except Exception as exc:  # intentionally sanitized
            local["status"] = "AI_AUDITOR_UNAVAILABLE"
            local["accuracy_notes"].append(f"OpenAI auditor unavailable: {exc.__class__.__name__}")
            return _force_safe_audit(local, original_signal=signal or {})

    def diagnose_error(self, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.auditor_enabled:
            return _safe_diagnosis("ERROR_DOCTOR_UNAVAILABLE", "OPENAI", "OpenAI auditor disabled", context)
        if not self.config.api_key:
            return _safe_diagnosis("ISSUE_FOUND", "OPENAI", "OPENAI_API_KEY is missing", context)
        try:
            payload = self._call_openai_json(_diagnosis_prompt(context or {}))
            return _validate_diagnosis_payload(payload, context)
        except Exception as exc:
            return _safe_diagnosis("ERROR_DOCTOR_UNAVAILABLE", "OPENAI", f"OpenAI diagnosis unavailable: {exc.__class__.__name__}", context)

    def _call_openai_json(self, prompt: str) -> Mapping[str, Any]:
        request_payload = {
            "model": self.config.model,
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
        }
        if self._transport is not None:
            result = self._transport(request_payload, self.config)
            return _extract_json_mapping(result)

        data = json.dumps(request_payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310 - fixed OpenAI endpoint
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenAI network unavailable") from exc
        return _extract_json_mapping(json.loads(raw))


def get_openai_auditor_config(env: Mapping[str, str] | None = None) -> OpenAIAuditorConfig:
    source = env or os.environ
    return OpenAIAuditorConfig(
        api_key=(source.get("OPENAI_API_KEY") or "").strip(),
        model=(source.get("OPENAI_MODEL") or "gpt-5.1-mini").strip() or "gpt-5.1-mini",
        auditor_enabled=_env_true(source.get("OPENAI_AUDITOR_ENABLED", "true")),
        autofix_enabled=False,
        can_modify_files=False,
        can_place_orders=False,
        go_live_allowed=False,
    )


def mask_openai_key(key: str | None) -> str:
    value = (key or "").strip()
    if not value:
        return "EMPTY"
    if len(value) <= 10:
        return f"SET-HIDDEN(len={len(value)})"
    return f"{value[:7]}...{value[-4:]}(len={len(value)})"


def openai_available(config: OpenAIAuditorConfig | None = None) -> bool:
    cfg = config or get_openai_auditor_config()
    return bool(cfg.auditor_enabled and cfg.api_key)


def audit_signal_with_openai(
    *,
    symbol: str = "RELIANCE",
    signal: Mapping[str, Any] | None = None,
    market_quote: Mapping[str, Any] | None = None,
    market_history: Mapping[str, Any] | None = None,
    config: OpenAIAuditorConfig | None = None,
) -> dict[str, Any]:
    return OpenAIReadOnlyAuditor(config).audit_signal(symbol=symbol, signal=signal or {}, market_quote=market_quote or {}, market_history=market_history or {})


def diagnose_error_with_openai(context: Mapping[str, Any] | None = None, config: OpenAIAuditorConfig | None = None) -> dict[str, Any]:
    return OpenAIReadOnlyAuditor(config).diagnose_error(context or {})


def deterministic_signal_audit(
    *,
    symbol: str = "RELIANCE",
    signal: Mapping[str, Any] | None = None,
    market_quote: Mapping[str, Any] | None = None,
    market_history: Mapping[str, Any] | None = None,
    min_confidence: float | None = None,
    min_risk_reward: float | None = None,
) -> dict[str, Any]:
    signal = signal or {}
    quote = market_quote or {}
    history = market_history or {}
    min_conf = min_confidence if min_confidence is not None else _safe_float(os.environ.get("MIN_SIGNAL_CONFIDENCE"), 70.0)
    min_rr = min_risk_reward if min_risk_reward is not None else _safe_float(os.environ.get("MIN_RISK_REWARD"), 1.5)

    original = _canonical_action(signal)
    reasons: list[str] = []
    notes: list[str] = []

    if original in {DATA_UNAVAILABLE, "NO_TRADE"}:
        reasons.append(f"ORIGINAL_SIGNAL_{original}")

    quote_status = str(quote.get("validation_status", DATA_UNAVAILABLE)).upper()
    quote_connection = str(quote.get("connection_status", "")).upper()
    ltp = quote.get("ltp", quote.get("last_price"))
    if quote_status != "VALIDATED" or not isinstance(ltp, (int, float)):
        reasons.append("VALIDATED_QUOTE_REQUIRED")
    if "STALE" in quote_status or "STALE" in quote_connection:
        reasons.append("STALE_QUOTE_BLOCKED")

    history_status = str(history.get("validation_status", DATA_UNAVAILABLE)).upper()
    candles = history.get("candles") or []
    if history_status != "VALIDATED":
        reasons.append("VALIDATED_CANDLES_REQUIRED")
    if not isinstance(candles, (list, tuple)) or len(candles) < 21:
        reasons.append("MINIMUM_21_CANDLES_REQUIRED")

    confidence = _safe_float(signal.get("confidence_score", signal.get("confidence")), -1.0)
    if confidence < min_conf:
        reasons.append(f"CONFIDENCE_BELOW_{int(min_conf)}")

    entry = _safe_float(signal.get("entry"), 0.0)
    if entry <= 0:
        reasons.append("ENTRY_REQUIRED")

    stop_loss = _safe_float(signal.get("stop_loss"), 0.0)
    if stop_loss <= 0:
        reasons.append("STOP_LOSS_REQUIRED")

    target_1 = signal.get("target_1")
    targets = signal.get("targets")
    has_target = _safe_float(target_1, 0.0) > 0 or (isinstance(targets, (list, tuple)) and any(_safe_float(item, 0.0) > 0 for item in targets))
    if not has_target:
        reasons.append("TARGET_REQUIRED")

    risk_reward = _safe_float(signal.get("risk_reward"), 0.0)
    if risk_reward < min_rr:
        reasons.append(f"RISK_REWARD_BELOW_{min_rr}")

    regime = str(signal.get("regime", signal.get("market_regime", ""))).strip().upper()
    if regime in {"", DATA_UNAVAILABLE}:
        notes.append("Market regime unavailable; keep review strict.")

    if original == DATA_UNAVAILABLE or "VALIDATED_QUOTE_REQUIRED" in reasons or "VALIDATED_CANDLES_REQUIRED" in reasons:
        final = DATA_UNAVAILABLE
    elif reasons:
        final = "NO_TRADE"
    else:
        final = original if original in {"BUY", "SELL", "HOLD"} else "NO_TRADE"

    status = "PASS" if not reasons else "BLOCKED"
    if final in {"BUY", "SELL"}:
        notes.append("Signal passed deterministic safety checks; still requires human review before any real-money consideration.")
    return OpenAIAuditResult(
        status=status,
        auditor="LOCAL_DETERMINISTIC_AUDITOR",
        original_action=original,
        final_action=final,
        confidence_grade=_confidence_grade(confidence),
        blocked_reasons=tuple(dict.fromkeys(reasons)),
        accuracy_notes=tuple(dict.fromkeys(notes)),
        safe_fix_suggestions=tuple(_suggestions_for_reasons(reasons)),
        requires_human_review=True,
        can_place_real_order=False,
        go_live_allowed=False,
    ).as_dict()


def _audit_prompt(*, symbol: str, signal: Mapping[str, Any], market_quote: Mapping[str, Any], market_history: Mapping[str, Any]) -> str:
    safe_context = {
        "symbol": symbol,
        "signal": _strip_sensitive(signal),
        "market_quote": _strip_sensitive(market_quote),
        "market_history_summary": {
            "validation_status": market_history.get("validation_status"),
            "connection_status": market_history.get("connection_status"),
            "candle_count": len(market_history.get("candles") or []),
            "data_source": market_history.get("data_source"),
        },
    }
    return (
        "You are a read-only trading signal safety auditor. Return JSON only. "
        "Never place orders, never enable live trading, never invent data. "
        "You may only confirm a safe signal or downgrade it to NO_TRADE/DATA_UNAVAILABLE. "
        "Schema keys: status, auditor, original_action, final_action, confidence_grade, "
        "blocked_reasons, accuracy_notes, safe_fix_suggestions, requires_human_review, "
        "can_place_real_order, go_live_allowed. Context: " + json.dumps(safe_context, default=str)
    )


def _diagnosis_prompt(context: Mapping[str, Any]) -> str:
    return (
        "You are a read-only app error doctor for a paper/shadow trading platform. "
        "Return safe JSON only. Never expose secrets. Never modify files. Never place orders. "
        "Schema keys: status, category, root_cause, affected_endpoint, evidence, safe_fix_suggestions, "
        "safe_to_auto_patch, requires_human_approval, can_place_real_order, go_live_allowed. Context: "
        + json.dumps(_strip_sensitive(context), default=str)
    )


def _merge_ai_with_local(ai_payload: Mapping[str, Any], local: dict[str, Any], original_signal: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(local)
    merged["auditor"] = "OPENAI_READ_ONLY_AUDITOR"
    ai_status = str(ai_payload.get("status", "PASS")).upper()
    ai_final = str(ai_payload.get("final_action", local.get("final_action", "NO_TRADE"))).upper()
    ai_reasons = _as_list(ai_payload.get("blocked_reasons"))
    ai_notes = _as_list(ai_payload.get("accuracy_notes"))
    ai_suggestions = _as_list(ai_payload.get("safe_fix_suggestions"))

    if ai_status in _ALLOWED_STATUS:
        merged["status"] = "BLOCKED" if ai_status == "BLOCKED" else local.get("status", "PASS")
    if ai_final in _ALLOWED_ACTIONS:
        # AI can downgrade, never upgrade local unsafe output or original NO_TRADE/DATA_UNAVAILABLE.
        if local.get("status") == "PASS" and _canonical_action(original_signal) not in {"NO_TRADE", DATA_UNAVAILABLE}:
            merged["final_action"] = ai_final if ai_final in {"NO_TRADE", DATA_UNAVAILABLE, local.get("final_action")} else local.get("final_action")
    merged["blocked_reasons"] = list(dict.fromkeys(_as_list(local.get("blocked_reasons")) + ai_reasons))
    merged["accuracy_notes"] = list(dict.fromkeys(_as_list(local.get("accuracy_notes")) + ai_notes))
    merged["safe_fix_suggestions"] = list(dict.fromkeys(_as_list(local.get("safe_fix_suggestions")) + ai_suggestions))
    return merged


def _force_safe_audit(payload: Mapping[str, Any], *, original_signal: Mapping[str, Any]) -> dict[str, Any]:
    original = _canonical_action(original_signal) if not payload.get("original_action") else str(payload.get("original_action")).upper()
    final = str(payload.get("final_action", "NO_TRADE")).upper()
    status = str(payload.get("status", "BLOCKED")).upper()
    if status not in _ALLOWED_STATUS:
        status = "BLOCKED"
    if original not in _ALLOWED_ACTIONS:
        original = DATA_UNAVAILABLE
    if final not in _ALLOWED_ACTIONS:
        final = "NO_TRADE"
    if original in {"NO_TRADE", DATA_UNAVAILABLE} and final in {"BUY", "SELL"}:
        final = original
    if status != "PASS" and final in {"BUY", "SELL"}:
        final = "NO_TRADE"
    grade = str(payload.get("confidence_grade", DATA_UNAVAILABLE)).upper()
    if grade not in _ALLOWED_GRADES:
        grade = DATA_UNAVAILABLE
    return OpenAIAuditResult(
        status=status,
        auditor=str(payload.get("auditor", "OPENAI_READ_ONLY_AUDITOR")),
        original_action=original,
        final_action=final,
        confidence_grade=grade,
        blocked_reasons=tuple(_as_list(payload.get("blocked_reasons"))),
        accuracy_notes=tuple(_as_list(payload.get("accuracy_notes"))),
        safe_fix_suggestions=tuple(_as_list(payload.get("safe_fix_suggestions"))),
        requires_human_review=True,
        can_place_real_order=False,
        go_live_allowed=False,
    ).as_dict()


def _validate_diagnosis_payload(payload: Mapping[str, Any], context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    status = str(payload.get("status", "ISSUE_FOUND")).upper()
    if status not in {"PASS", "ISSUE_FOUND", "NO_LOG_AVAILABLE", "ERROR_DOCTOR_UNAVAILABLE"}:
        status = "ISSUE_FOUND"
    category = str(payload.get("category", "UNKNOWN")).upper()
    if category not in {"UI", "API", "BROKER", "DATA", "SIGNAL", "PAPER", "OPENAI", "UNKNOWN"}:
        category = "UNKNOWN"
    return {
        "status": status,
        "category": category,
        "root_cause": str(payload.get("root_cause", "Diagnosis unavailable"))[:1200],
        "affected_endpoint": str(payload.get("affected_endpoint", DATA_UNAVAILABLE))[:300],
        "evidence": _as_list(payload.get("evidence"))[:10],
        "safe_fix_suggestions": _as_list(payload.get("safe_fix_suggestions"))[:10],
        "safe_to_auto_patch": False,
        "requires_human_approval": True,
        "can_place_real_order": False,
        "go_live_allowed": False,
        "context_received": bool(context),
    }


def _safe_diagnosis(status: str, category: str, root_cause: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "category": category,
        "root_cause": root_cause,
        "affected_endpoint": DATA_UNAVAILABLE,
        "evidence": [] if context is None else ["context provided"],
        "safe_fix_suggestions": [],
        "safe_to_auto_patch": False,
        "requires_human_approval": True,
        "can_place_real_order": False,
        "go_live_allowed": False,
    }


def _extract_json_mapping(value: Mapping[str, Any] | str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        if isinstance(value.get("output_text"), str):
            return _extract_json_mapping(value["output_text"])
        if "status" in value or "final_action" in value or "root_cause" in value:
            return value
        for item in value.get("output", []) if isinstance(value.get("output"), list) else []:
            for content in item.get("content", []) if isinstance(item, Mapping) else []:
                if isinstance(content, Mapping) and isinstance(content.get("text"), str):
                    return _extract_json_mapping(content["text"])
    if isinstance(value, str):
        return json.loads(value)
    raise ValueError("Invalid OpenAI JSON payload")


def _canonical_action(signal: Mapping[str, Any]) -> str:
    action = str(signal.get("final_action", signal.get("decision", signal.get("action", DATA_UNAVAILABLE)))).strip().upper()
    return action if action in _ALLOWED_ACTIONS else DATA_UNAVAILABLE


def _confidence_grade(confidence: float) -> str:
    if confidence < 0:
        return DATA_UNAVAILABLE
    if confidence >= 90:
        return "A"
    if confidence >= 80:
        return "B"
    if confidence >= 70:
        return "C"
    if confidence >= 60:
        return "D"
    return "F"


def _suggestions_for_reasons(reasons: list[str]) -> list[str]:
    suggestions: list[str] = []
    joined = " ".join(reasons)
    if "QUOTE" in joined:
        suggestions.append("Verify Zerodha access token and /api/broker/quote before auditing signals.")
    if "CANDLE" in joined:
        suggestions.append("Download NSE instruments.csv and verify historical candles endpoint.")
    if "CONFIDENCE" in joined:
        suggestions.append("Keep signal as NO_TRADE until confidence improves above configured threshold.")
    if "STOP_LOSS" in joined or "TARGET" in joined or "RISK_REWARD" in joined:
        suggestions.append("Require complete entry, stop-loss, target, and risk-reward before any paper/shadow action.")
    return suggestions


def _strip_sensitive(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            upper = str(key).upper()
            if any(secret in upper for secret in ("TOKEN", "SECRET", "API_KEY", "PASSWORD", "AUTHORIZATION")):
                result[str(key)] = "SET-HIDDEN" if value else "EMPTY"
            else:
                result[str(key)] = _strip_sensitive(value)
        return result
    if isinstance(payload, (list, tuple)):
        return [_strip_sensitive(item) for item in payload[:50]]
    return payload


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _env_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}
