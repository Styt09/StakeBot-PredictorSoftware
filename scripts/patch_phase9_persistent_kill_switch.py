from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .persistent_kill_switch import PersistentKillSwitch, block_payload\n"

HELPER = r'''

_PERSISTENT_KILL_SWITCH = PersistentKillSwitch()

def _persistent_kill_switch_status() -> dict[str, Any]:
    return _PERSISTENT_KILL_SWITCH.status()

def _persistent_kill_switch_active() -> bool:
    return bool(_PERSISTENT_KILL_SWITCH.is_active())

def _persistent_kill_switch_activate(payload: dict[str, Any]) -> dict[str, Any]:
    return _PERSISTENT_KILL_SWITCH.activate(payload)

def _persistent_kill_switch_reset(payload: dict[str, Any]) -> dict[str, Any]:
    return _PERSISTENT_KILL_SWITCH.reset(payload)
'''

CARD = '''
<section class="card strong shadow" id="persistent-kill-switch-card"><span class="badge danger">PERSISTENT KILL SWITCH</span><span class="badge warn">FAIL CLOSED</span><h2>Durable Safety Stop</h2><p class="muted">Active state survives restart and blocks new paper/shadow/future-live order paths.</p><div id="persistent-kill-switch-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadPersistentKillSwitchCard(){fetch('/api/kill-switch/status').then(r=>r.json()).then(p=>{const el=document.getElementById('persistent-kill-switch-kv');if(!el)return;el.innerHTML=`<div><strong>active</strong>${p.active}</div><div><strong>reason</strong>${p.reason||'NONE'}</div><div><strong>activated_at</strong>${p.activated_at||'NONE'}</div><div><strong>reset_at</strong>${p.reset_at||'NONE'}</div><div><strong>event_id</strong>${p.event_id||'NONE'}</div><div><strong>go_live_allowed</strong>${p.go_live_allowed}</div>`}).catch(()=>{})}
setInterval(loadPersistentKillSwitchCard,5000);loadPersistentKillSwitchCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase9_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if "_PERSISTENT_KILL_SWITCH = PersistentKillSwitch()" not in text:
        text = text.replace('\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', HELPER + '\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', 1)

    if 'path == "/api/kill-switch/status"' not in text:
        marker_get = '        elif path == "/api/broker/health":\n            self._send_json(200, _broker_adapter().health())\n'
        insert_get = '        elif path == "/api/kill-switch/status":\n            self._send_json(200, _persistent_kill_switch_status())\n' + marker_get
        if marker_get not in text:
            raise SystemExit("broker health route marker not found; apply phase8 first")
        text = text.replace(marker_get, insert_get, 1)

    if 'path == "/api/kill-switch/activate"' not in text:
        marker_post = '        elif path == "/api/live/kill-switch":\n            self._send_json(200, _live_kill_switch(payload))\n'
        insert_post = '        elif path == "/api/kill-switch/activate":\n            self._send_json(200, _persistent_kill_switch_activate(payload))\n        elif path == "/api/kill-switch/reset":\n            self._send_json(200, _persistent_kill_switch_reset(payload))\n' + marker_post
        if marker_post not in text:
            raise SystemExit("live kill switch route marker not found")
        text = text.replace(marker_post, insert_post, 1)

    if 'kill_switch_active=_kill_switch_active() or _persistent_kill_switch_active()' not in text:
        text = text.replace('kill_switch_active=_kill_switch_active(),', 'kill_switch_active=_kill_switch_active() or _persistent_kill_switch_active(),')

    if 'if _persistent_kill_switch_active():\n            self._send_json(200, {"status": "BLOCKED", "reason": "KILL_SWITCH_ACTIVE", "blocked_reasons": ("KILL_SWITCH_ACTIVE",), "go_live_allowed": False})' not in text:
        paper_marker = '        elif path == "/api/paper/order":\n'
        if paper_marker in text:
            text = text.replace(paper_marker, paper_marker + '            if _persistent_kill_switch_active():\n                self._send_json(200, {"status": "BLOCKED", "reason": "KILL_SWITCH_ACTIVE", "blocked_reasons": ("KILL_SWITCH_ACTIVE",), "go_live_allowed": False})\n                return\n', 1)
        shadow_marker = '        elif path == "/api/shadow/evaluate":\n            self._send_json(200, _shadow_evaluate(payload))\n'
        if shadow_marker in text:
            text = text.replace(shadow_marker, '        elif path == "/api/shadow/evaluate":\n            if _persistent_kill_switch_active():\n                self._send_json(200, {"status": "SHADOW_BLOCKED", "reason": "KILL_SWITCH_ACTIVE", "blocked_reasons": ("KILL_SWITCH_ACTIVE",), "go_live_allowed": False})\n            else:\n                self._send_json(200, _shadow_evaluate(payload))\n', 1)

    if 'id="persistent-kill-switch-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)

    if "loadPersistentKillSwitchCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)

    WEB_APP.write_text(text)
    print(f"PHASE9_PERSISTENT_KILL_SWITCH_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
