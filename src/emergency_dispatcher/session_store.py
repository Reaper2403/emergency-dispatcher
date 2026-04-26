from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import REPO_ROOT


SESSION_DIR = REPO_ROOT / "runs" / "sessions"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def session_path(session_id: str) -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR / f"{session_id}.json"


def _read_session(session_id: str) -> dict[str, Any]:
    path = session_path(session_id)
    if not path.exists():
        return {
            "session_id": session_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "server": {},
            "client": {},
            "tool_calls": [],
            "triage_turns": [],
            "merged_triage_state": {},
            "rule_overrides": [],
            "handoff_packet": None,
            "triage_meta": {},
            "stt_rescue_events": [],
            "stt_rescue_overrides": {},
            "stt_rescue_meta": {},
            "llm_prompt_snapshots": [],
            "dispatch_services": {},
            "dispatch_prompt_context": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _write_session(session_id: str, payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    session_path(session_id).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _merge_dict(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


class SessionRecorder:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.ensure_exists()

    def ensure_exists(self) -> None:
        payload = _read_session(self.session_id)
        _write_session(self.session_id, payload)

    def patch_server(self, patch: dict[str, Any]) -> None:
        payload = _read_session(self.session_id)
        payload["server"] = _merge_dict(payload.get("server", {}), patch)
        _write_session(self.session_id, payload)

    def patch_session(self, patch: dict[str, Any]) -> None:
        payload = _read_session(self.session_id)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(payload.get(key), dict):
                payload[key] = _merge_dict(payload.get(key, {}), value)
            else:
                payload[key] = value
        _write_session(self.session_id, payload)

    def append_tool_call(
        self,
        *,
        name: str,
        args: dict[str, Any],
        result: dict[str, Any] | None = None,
        error: str | None = None,
        started_at: str | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        payload = _read_session(self.session_id)
        payload.setdefault("tool_calls", []).append(
            {
                "at": utc_now(),
                "started_at": started_at,
                "name": name,
                "args": args,
                "result": result,
                "error": error,
                "elapsed_ms": elapsed_ms,
            }
        )
        _write_session(self.session_id, payload)

    def append_session_list(self, key: str, entry: dict[str, Any]) -> None:
        payload = _read_session(self.session_id)
        payload.setdefault(key, []).append(entry)
        _write_session(self.session_id, payload)

    def patch_client_report(self, report: dict[str, Any]) -> None:
        payload = _read_session(self.session_id)
        payload["client"] = _merge_dict(payload.get("client", {}), report)
        _write_session(self.session_id, payload)


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        SESSION_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    sessions: list[dict[str, Any]] = []
    for path in files[:limit]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        sessions.append(
            {
                "session_id": payload.get("session_id"),
                "updated_at": payload.get("updated_at"),
                "created_at": payload.get("created_at"),
                "server_status": payload.get("server", {}).get("status"),
                "client_status": payload.get("client", {}).get("status"),
                "user_turns": len(payload.get("client", {}).get("transcripts", {}).get("user", [])),
                "agent_turns": len(payload.get("client", {}).get("transcripts", {}).get("agent", [])),
                "tool_call_count": len(payload.get("tool_calls", [])),
                "triage_turn_count": len(payload.get("triage_turns", [])),
            }
        )
    return sessions


def get_session(session_id: str) -> dict[str, Any]:
    return _read_session(session_id)
