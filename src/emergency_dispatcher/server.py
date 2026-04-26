from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import gradbot
import httpx
from fastapi import Body
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import WebSocket
from fastapi import WebSocketException
from fastapi import status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .gradbot_adapter import build_session_config
from .dispatch_tools import assess_searchable_location_query
from .dispatch_tools import dispatch_tool_call
from .dispatch_tools import extract_address_candidate
from .enhanced_audio import finalize_audio_artifacts
from .enhanced_audio import make_enhancer
from .enhanced_audio import PCM_SAMPLE_RATE
from .session_store import SessionRecorder
from .session_store import get_session
from .session_store import list_sessions
from .session_store import utc_now
from .settings import get_settings
from .slm_fact_ledger import build_fact_priority_packet
from .slm_fact_ledger import build_ledger_prompt_context
from .slm_fact_ledger import classify_location_kind
from .slm_fact_ledger import empty_shared_ledger
from .slm_fact_ledger import fact_ledger_to_shared_hard_facts
from .slm_fact_ledger import FACT_LEDGER_SYSTEM_PROMPT
from .slm_fact_ledger import FactLedger
from .slm_fact_ledger import has_dispatchable_location_cue
from .slm_fact_ledger import is_immediate_fact_ledger_trigger
from .slm_fact_ledger import is_trivial_caller_turn
from .slm_fact_ledger import latest_substantive_caller_window
from .slm_fact_ledger import normalize_shared_ledger
from .slm_fact_ledger import shared_hard_facts_to_fact_ledger
from .stt_rescue import append_live_audio_window
from .stt_rescue import clear_live_audio_window
from .stt_rescue import maybe_run_stt_rescue
from .stt_rescue import stt_rescue_session_patch
from .triage import analyze_session_triage
from .triage import triage_session_patch


app = FastAPI(title="Emergency Dispatcher")
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
GRADBOT_JS_DIR = Path(gradbot.routes.__file__).resolve().parent / "js_audio"

app.mount("/demo-static", StaticFiles(directory=FRONTEND_DIR), name="demo_static")
app.mount("/static/js", StaticFiles(directory=GRADBOT_JS_DIR), name="gradbot_js")

AUTO_PIN_SAFE_LOCATION_REASONS = {
    "explicit_address",
    "street_number",
}
AUTO_LOCATION_HINT_PATTERN = re.compile(
    r"\b(?:on|at|near|close to|around|inside|in)\s+([A-Za-z0-9.\-'\s]{3,80}?)(?=[,.!?]|$)",
    re.IGNORECASE,
)
AUTO_SUB_LOCATION_PATTERN = re.compile(
    r"\b(\d+(?:st|nd|rd|th)\s+floor|first floor|second floor|third floor|fourth floor|room\s+\w+|unit\s+\w+|stairwell|entrance|gate|lobby|basement)\b",
    re.IGNORECASE,
)
AUTO_EMERGENCY_CONTEXT_PATTERN = re.compile(
    r"\b("
    r"accident|crash|collision|hit|rolled over|upside down|"
    r"not responding|unresponsive|unconscious|not moving|"
    r"bleeding|blood|injured|injury|hurt|trapped|stuck|"
    r"fire|smoke|burning|gas leak|explosion|"
    r"gun|weapon|knife|hostage|armed|shooting|"
    r"breathing|not breathing|can't breathe|cannot breathe"
    r")\b",
    re.IGNORECASE,
)
SEMANTIC_NEGATION_VALUE_MAP = {
    "yes": "yes",
    "no": "no",
}
LEDGER_BINARY_FIELDS = {
    "child_present",
    "bleeding_status",
    "breathing_status",
    "consciousness_status",
    "trapped_status",
}
LEDGER_LOCATION_SAFE_KINDS = {"exact_address", "road_or_junction", "place_name"}
LOCATION_QUESTION_PATTERNS = {
    "ask_where": re.compile(r"\bwhere are you(?: right now)?\b", re.IGNORECASE),
    "ask_exact_address": re.compile(
        r"\b(?:exact address|what(?:'s| is)? the address|know the exact address|what address)\b",
        re.IGNORECASE,
    ),
    "confirm_candidate": re.compile(
        r"\b(?:you said|did you say|is that correct|is that right|correct\?)\b",
        re.IGNORECASE,
    ),
    "ask_spell": re.compile(r"\bspell\b", re.IGNORECASE),
    "ask_landmark": re.compile(
        r"\b(?:landmark|describe your surroundings|what do you see|what is around you|what's around you|road sign)\b",
        re.IGNORECASE,
    ),
}
LOCATION_DEAD_END_ATTEMPTS = 4
LOCATION_KIND_STRENGTH = {
    "none": 0,
    "vague": 0,
    "sub_location_only": 1,
    "place_name": 2,
    "road_or_junction": 3,
    "exact_address": 4,
}
LEDGER_JOB_REGISTRY: dict[str, dict[str, Any]] = {}


def _run_kwargs() -> dict[str, Any]:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "gradium_api_key": settings.gradium_api_key,
    }
    llm_base_url = settings.openai_base_url or (
        "https://api.openai.com/v1" if settings.openai_api_key else None
    )
    if llm_base_url:
        kwargs["llm_base_url"] = llm_base_url
    if settings.openai_model:
        kwargs["llm_model_name"] = settings.openai_model
    if settings.openai_api_key:
        kwargs["llm_api_key"] = settings.openai_api_key
    return kwargs


def _ensure_llm_ready() -> Any:
    settings = get_settings()
    if not settings.openai_model or not settings.openai_api_key:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=(
                "Missing OPENAI_MODEL or OPENAI_API_KEY. "
                "Set an OpenAI-compatible LLM endpoint before starting the live voice demo."
            ),
        )
    return settings


def _resolve_live_dispatch_mode(value: Any | None = None) -> str:
    settings = get_settings()
    normalized = str(value or settings.live_dispatch_mode or "slm").strip().lower().replace("-", "_")
    if normalized in {"off", "none", "disabled", "llm", "llm_only"}:
        return "llm_only"
    return "slm"


def _live_triage_settings() -> Any:
    return get_settings().model_copy(update={"triage_engine": "slm"})


def _fact_ledger_model_id(settings: Any) -> str | None:
    return settings.live_fact_ledger_model or settings.triage_decoder_model


def _live_triage_missing(settings) -> list[str]:
    missing: list[str] = []
    if not settings.triage_api_key:
        missing.append("TRIAGE_API_KEY")
    if not _fact_ledger_model_id(settings):
        missing.append("LIVE_FACT_LEDGER_MODEL")
    return missing


def _ensure_live_triage_ready_http():
    settings = _live_triage_settings()
    missing = _live_triage_missing(settings)
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                "Live triage is pinned to the Pioneer SLM path. "
                f"Missing required config: {', '.join(missing)}."
            ),
        )
    return settings


def _ensure_live_triage_ready_ws():
    settings = _live_triage_settings()
    missing = _live_triage_missing(settings)
    if missing:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=(
                "Live triage is pinned to the Pioneer SLM path. "
                f"Missing required config: {', '.join(missing)}."
            ),
        )
    return settings


def _live_runtime_settings(mode: str) -> Any:
    if mode == "slm":
        return _live_triage_settings()
    return get_settings().model_copy(update={"triage_engine": "heuristic"})


def _ensure_live_runtime_ready_http(mode: str):
    if mode == "slm":
        return _ensure_live_triage_ready_http()
    return _live_runtime_settings(mode)


def _ensure_live_runtime_ready_ws(mode: str):
    if mode == "slm":
        return _ensure_live_triage_ready_ws()
    return _live_runtime_settings(mode)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "emergency-dispatcher",
        "status": "ready",
        "websocket": "/ws",
        "demo": "/demo",
        "review": "/review",
    }


@app.get("/api/audio-config")
def audio_config() -> dict[str, Any]:
    return {
        "pcm": True,
        "pcm_input": True,
        "sample_rate": PCM_SAMPLE_RATE,
        "channels": 1,
        "chunk_samples": 1920,
    }


@app.get("/demo")
def demo() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/review")
def review() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "review.html")


@app.post("/api/session-report")
async def session_report(report: dict[str, Any] = Body(...)) -> dict[str, Any]:
    live_dispatch_mode = _resolve_live_dispatch_mode(report.get("triage_mode"))
    triage_settings = _ensure_live_runtime_ready_http(live_dispatch_mode)
    session_id = report.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    recorder = SessionRecorder(session_id)
    recorder.patch_client_report(report)
    recorder.patch_server(
        {
            "triage_engine": live_dispatch_mode,
            "live_dispatch_mode": live_dispatch_mode,
        }
    )
    session = get_session(session_id)
    stt_rescue_event = await maybe_run_stt_rescue(
        session_id=session_id,
        session=session,
        settings=triage_settings,
    )
    if stt_rescue_event is not None:
        recorder.patch_session(stt_rescue_session_patch(session, stt_rescue_event))
        session = get_session(session_id)
    if live_dispatch_mode == "llm_only":
        _auto_follow_location_resolution(session, recorder)
        session = get_session(session_id)
        dispatch_update = _auto_dispatch_services(session, recorder)
        return {
            "status": "ok",
            "triage_mode": live_dispatch_mode,
            "triage_enabled": False,
            "triage_update": None,
            "dispatch_update": dispatch_update,
            "triage_meta": {
                "selected_engine": "llm_only",
                "runtime_provider": "gradium",
                "dispatchable": False,
                "autonomy_allowed": True,
                "missing_or_unknown_fields": [],
            },
            "stt_rescue_meta": session.get("stt_rescue_meta") or {},
            "stt_rescue_event": stt_rescue_event.model_dump() if stt_rescue_event else None,
        }
    if not session.get("shared_ledger"):
        recorder.patch_session({"shared_ledger": empty_shared_ledger()})
        session = get_session(session_id)
    ledger = _refresh_shared_ledger_runtime(session, recorder)
    session = get_session(session_id)
    _schedule_shared_ledger_refresh(session_id, triage_settings)
    dispatch_update = _auto_dispatch_services(session, recorder)
    return {
        "status": "ok",
        "triage_update": None,
        "ledger_update": {
            "version": ledger.get("version"),
            "prompt_context": build_ledger_prompt_context(ledger),
        },
        "dispatch_update": dispatch_update,
        "triage_meta": {
            "selected_engine": "shared_ledger_slm",
            "runtime_provider": "pioneer",
            "dispatchable": bool(session.get("dispatch_services", {}).get("dispatchable")),
            "autonomy_allowed": True,
            "missing_or_unknown_fields": list((ledger.get("priority") or {}).get("missing_fields") or []),
        },
        "stt_rescue_event": stt_rescue_event.model_dump() if stt_rescue_event else None,
    }


@app.get("/api/sessions")
def api_sessions() -> list[dict[str, Any]]:
    return list_sessions()


@app.get("/api/sessions/{session_id}")
def api_session_detail(session_id: str) -> dict[str, Any]:
    return get_session(session_id)


def _record_tool_result(
    recorder: SessionRecorder | None,
    *,
    name: str,
    args: dict[str, Any],
    result: dict[str, Any] | None = None,
    error: str | None = None,
    started_at: str | None = None,
    elapsed_ms: int | None = None,
) -> None:
    if recorder is None:
        return
    recorder.append_tool_call(
        name=name,
        args=args,
        result=result,
        error=error,
        started_at=started_at,
        elapsed_ms=elapsed_ms,
    )


def _normalize_runtime_text(value: Any | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sanitize_location_candidate_text(value: Any | None) -> str | None:
    normalized = _normalize_runtime_text(value)
    if not normalized:
        return None
    normalized = re.sub(
        r"^(?:please\s+)?(?:find|search(?: for)?|look up|locate|pin|send help to|route to)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:near|close to|around|by|outside|inside|at|to|toward|towards)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = normalized.strip(" ,.")
    return normalized or None


def _looks_like_non_location_speech(value: Any | None) -> bool:
    candidate = _normalize_runtime_text(value)
    if not candidate:
        return True
    lowered = candidate.casefold()
    if "?" in candidate:
        return True
    if lowered in {
        "nearest landmark",
        "exact address",
        "the exact address",
        "a broken knee",
        "broken knee",
        "need help",
        "help me",
    }:
        return True
    if re.match(r"^(?:hello|hi|hey)\b", lowered):
        return True
    if re.match(r"^(?:can you|could you|will you|would you|do you|are you|please|thanks|thank you)\b", lowered):
        return True
    if re.match(r"^(?:have|has|had)\b", lowered):
        return True
    return False


def _best_effort_runtime_location_candidate(value: Any | None) -> str | None:
    candidate = _sanitize_location_candidate_text(value)
    if not candidate:
        return None
    if _looks_like_non_location_speech(candidate):
        return None
    lowered = candidate.casefold()
    if len(lowered) < 4:
        return None
    generic_phrases = {
        "here",
        "at home",
        "home",
        "inside the building",
        "inside",
        "somewhere in berlin",
        "in the middle of the street",
        "middle of the street",
    }
    if lowered in generic_phrases:
        return None
    raw_tokens = [token for token in re.split(r"[\s,./-]+", lowered) if token]
    if len(raw_tokens) < 2:
        return None
    filtered_tokens = [
        token
        for token in raw_tokens
        if token not in {"me", "you", "we", "they", "there", "here", "around", "near", "close", "to", "at", "on", "in", "is", "am", "are", "the", "a", "an", "my", "your"}
        and token not in {"strasse", "straße", "allee", "platz", "ring", "ufer", "damm"}
    ]
    if len(filtered_tokens) < 2:
        return None
    place_hint_tokens = {
        "strasse",
        "straße",
        "allee",
        "platz",
        "ring",
        "ufer",
        "damm",
        "campus",
        "park",
        "gate",
        "bahnhof",
        "station",
        "feld",
        "theater",
        "theatre",
        "mall",
        "hospital",
        "school",
        "center",
        "centre",
        "tower",
        "tor",
    }
    if not any(token in place_hint_tokens for token in raw_tokens):
        return None
    if all(
        token in {
            "accident",
            "collision",
            "smoke",
            "fire",
            "bleeding",
            "blood",
            "trapped",
            "stuck",
            "hurt",
            "help",
            "daughter",
            "wife",
            "husband",
            "child",
            "people",
            "person",
        }
        for token in filtered_tokens
    ):
        return None
    return candidate


def _meaningful_runtime_location_candidate(value: Any | None) -> str | None:
    candidate = _sanitize_location_candidate_text(value)
    if not candidate:
        return None
    if _looks_like_non_location_speech(candidate):
        return None
    lowered = candidate.casefold()
    if re.match(r"^(?:there is|there's|i am|i'm|hello|help)\b", lowered):
        return None
    noisy_tokens = {
        "there",
        "is",
        "smoke",
        "fire",
        "bleeding",
        "blood",
        "trapped",
        "stuck",
        "accident",
        "collision",
        "hurt",
        "daughter",
        "wife",
        "husband",
        "people",
        "involved",
        "around",
        "me",
    }
    tokens = [token for token in re.split(r"[\s,./-]+", lowered) if token]
    if len(tokens) > 3 and sum(token in noisy_tokens for token in tokens) >= 2:
        return None
    allowed, _reason = assess_searchable_location_query(candidate)
    if allowed:
        return candidate
    return None


def _runtime_location_candidate_kind(value: Any | None) -> str:
    candidate = _sanitize_location_candidate_text(value)
    if not candidate:
        return "none"
    kind = classify_location_kind(candidate)
    if kind != "none":
        return kind
    if _best_effort_runtime_location_candidate(candidate):
        lowered = candidate.casefold()
        if any(lowered.endswith(suffix) for suffix in ("strasse", "straße", "allee", "platz", "ring", "ufer", "damm")):
            return "road_or_junction"
        return "place_name"
    return "none"


def _has_emergency_context(transcript: str | None) -> bool:
    normalized = _normalize_runtime_text(transcript)
    if not normalized:
        return False
    if AUTO_EMERGENCY_CONTEXT_PATTERN.search(normalized):
        return True
    # Avoid triggering lookup/ticket automation on line checks or bare place mentions.
    return len(normalized.split()) >= 12 and bool(extract_address_candidate(normalized))


def _latest_tool_call(session: dict[str, Any], *names: str) -> dict[str, Any] | None:
    allowed = set(names)
    for tool_call in reversed(session.get("tool_calls") or []):
        if tool_call.get("name") in allowed:
            return tool_call
    return None


def _has_tool_call_for_query(session: dict[str, Any], names: tuple[str, ...], query: str) -> bool:
    normalized_query = _normalize_runtime_text(query).casefold()
    for tool_call in reversed(session.get("tool_calls") or []):
        if tool_call.get("name") not in names:
            continue
        args = tool_call.get("args") or {}
        candidate = args.get("address_text") or args.get("location_candidate") or ""
        if _normalize_runtime_text(candidate).casefold() == normalized_query:
            return True
    return False


def _has_tool_call_for_coords(session: dict[str, Any], name: str, lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    target = (round(float(lat), 4), round(float(lon), 4))
    for tool_call in reversed(session.get("tool_calls") or []):
        if tool_call.get("name") != name:
            continue
        args = tool_call.get("args") or {}
        item_lat = args.get("lat")
        item_lon = args.get("lon")
        if item_lat is None or item_lon is None:
            continue
        candidate = (round(float(item_lat), 4), round(float(item_lon), 4))
        if candidate == target:
            return True
    return False


def _infer_location_bundle_from_text(text: str) -> tuple[str | None, str | None, str | None]:
    normalized = _normalize_runtime_text(text)
    if not normalized:
        return None, None, None

    sub_location_match = AUTO_SUB_LOCATION_PATTERN.search(normalized)
    sub_location = _normalize_runtime_text(sub_location_match.group(1)) if sub_location_match else None

    address = extract_address_candidate(normalized)
    if address:
        return _sanitize_location_candidate_text(address), normalized, sub_location

    matches = list(AUTO_LOCATION_HINT_PATTERN.finditer(normalized))
    for match in reversed(matches):
        candidate = _normalize_runtime_text(match.group(1))
        if not candidate:
            continue
        if re.match(r"^(?:me|you|we|they|here|there)\b", candidate, flags=re.IGNORECASE):
            continue
        if sub_location and sub_location.casefold() in candidate.casefold():
            candidate = _normalize_runtime_text(re.sub(re.escape(sub_location), "", candidate, flags=re.IGNORECASE))
        candidate = re.split(r"\b(?:and|but|only|except|with)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.")
        strong_candidate = _meaningful_runtime_location_candidate(candidate)
        if strong_candidate:
            return strong_candidate, normalized, sub_location
        best_effort_candidate = _best_effort_runtime_location_candidate(candidate)
        if best_effort_candidate:
            return best_effort_candidate, normalized, sub_location

    direct_candidate = _meaningful_runtime_location_candidate(normalized)
    if direct_candidate and len(normalized.split()) <= 6:
        note = normalized if direct_candidate.casefold() != normalized.casefold() else None
        return direct_candidate, note, sub_location
    direct_best_effort = _best_effort_runtime_location_candidate(normalized)
    if direct_best_effort and len(normalized.split()) <= 6:
        note = normalized if direct_best_effort.casefold() != normalized.casefold() else None
        return direct_best_effort, note, sub_location

    if has_dispatchable_location_cue(normalized) or sub_location:
        return None, normalized, sub_location
    return None, None, sub_location


def _infer_location_bundle_from_transcript(session: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    turns = session.get("client", {}).get("transcripts", {}).get("user", []) or []
    snippets = [_normalize_runtime_text(turn.get("text")) for turn in turns if _normalize_runtime_text(turn.get("text"))]
    if not snippets:
        return None, None, None
    combined = " ".join(snippets[-6:])
    sub_location_match = AUTO_SUB_LOCATION_PATTERN.search(combined)
    sub_location = _normalize_runtime_text(sub_location_match.group(1)) if sub_location_match else None
    address = extract_address_candidate(combined)
    if address:
        return _sanitize_location_candidate_text(address), combined, sub_location
    for text in reversed(snippets[-8:]):
        candidate, note, inferred_sub = _infer_location_bundle_from_text(text)
        if candidate or note or inferred_sub:
            return candidate, note, inferred_sub or sub_location
    return None, None, sub_location


def _latest_transcript_items(session: dict[str, Any], role: str) -> list[dict[str, Any]]:
    items = session.get("client", {}).get("transcripts", {}).get(role, []) or []
    return list(items) if isinstance(items, list) else []


def _location_question_kind(text: str | None) -> str | None:
    normalized = _normalize_runtime_text(text)
    if not normalized:
        return None
    for kind, pattern in LOCATION_QUESTION_PATTERNS.items():
        if pattern.search(normalized):
            return kind
    return None


def _location_attempt_state(session: dict[str, Any]) -> tuple[int, str | None]:
    attempts = 0
    last_kind = None
    for turn in _latest_transcript_items(session, "agent")[-12:]:
        kind = _location_question_kind(turn.get("text"))
        if kind:
            attempts += 1
            last_kind = kind
    return attempts, last_kind


def _last_user_response_text(session: dict[str, Any]) -> str | None:
    for turn in reversed(_latest_transcript_items(session, "user")):
        text = _normalize_runtime_text(turn.get("text"))
        if text:
            return text
    return None


def _latest_location_response_text(session: dict[str, Any]) -> str | None:
    last_kind = None
    for turn in reversed(_latest_transcript_items(session, "agent")):
        kind = _location_question_kind(turn.get("text"))
        if kind:
            last_kind = kind
            break
    if not last_kind:
        return None
    text = _last_user_response_text(session)
    if not text or is_trivial_caller_turn(text):
        return None
    return text


def _infer_shared_ledger_location_bundle(session: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    turns = _latest_transcript_items(session, "user")
    substantive_turns = [
        _normalize_runtime_text(turn.get("text"))
        for turn in turns
        if _normalize_runtime_text(turn.get("text"))
    ]
    combined = " ".join(substantive_turns[-18:])
    sub_location_match = AUTO_SUB_LOCATION_PATTERN.search(combined)
    sub_location = _normalize_runtime_text(sub_location_match.group(1)) if sub_location_match else None

    latest_location_response = _latest_location_response_text(session)
    if latest_location_response:
        candidate, note, latest_sub_location = _infer_location_bundle_from_text(latest_location_response)
        if candidate or note or latest_sub_location:
            return candidate, note or latest_location_response, latest_sub_location or sub_location

    for text in reversed(substantive_turns[-8:]):
        if not text or is_trivial_caller_turn(text):
            continue
        if has_dispatchable_location_cue(text):
            candidate, note, latest_sub_location = _infer_location_bundle_from_text(text)
            if candidate:
                return candidate, note or text, latest_sub_location or sub_location
            return None, text, sub_location
    candidate, note, inferred_sub = _infer_location_bundle_from_transcript(session)
    return candidate, note, inferred_sub or sub_location


def _location_followup_prompt(
    kind: str | None,
    candidate_text: str | None = None,
    *,
    candidate_source: str | None = None,
) -> str | None:
    if kind == "ask_where":
        return "Where are you right now?"
    if kind == "ask_exact_address":
        return "Do you know the exact address? If you do, say it slowly."
    if kind == "confirm_candidate" and candidate_text:
        if candidate_source == "maps_candidate":
            return f"I found {candidate_text}. Is that correct? Yes or no."
        return f"You said {candidate_text}. Is that correct? Yes or no."
    if kind == "ask_spell":
        return "Please spell the street or place name slowly for me."
    if kind == "ask_landmark":
        return "Tell me the nearest landmark you know and describe what you see around you."
    return None


def _build_location_followup_state(session: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    hard_facts = ledger.get("hard_facts") or {}
    location_gate = ledger.get("location_gate") or {}
    inferred_candidate, inferred_note, inferred_sub_location = _infer_shared_ledger_location_bundle(session)
    resolve_call = _latest_tool_call(session, "resolve_location_note")
    resolve_result = (resolve_call or {}).get("result") or {}
    lookup_call = _latest_tool_call(session, "lookup_address")
    lookup_result = (lookup_call or {}).get("result") or {}
    lookup_candidate_text = None
    lookup_candidate_kind = None
    candidate_source = None
    if lookup_result.get("candidate_only") and lookup_result.get("normalized_address"):
        lookup_candidate_text = _sanitize_location_candidate_text(lookup_result.get("normalized_address"))
        lookup_candidate_kind = "exact_address" if lookup_candidate_text else None
        candidate_source = "maps_candidate"

    candidate_text = (
        lookup_candidate_text
        or
        _meaningful_runtime_location_candidate(resolve_result.get("anchor_location"))
        or _meaningful_runtime_location_candidate(inferred_candidate)
        or _meaningful_runtime_location_candidate(hard_facts.get("location_candidate"))
        or None
    )
    note_text = (
        _normalize_runtime_text(hard_facts.get("location_note"))
        or _normalize_runtime_text(inferred_note)
        or _normalize_runtime_text(resolve_result.get("normalized_note"))
        or None
    )
    sub_location = (
        _normalize_runtime_text(hard_facts.get("sub_location"))
        or _normalize_runtime_text(inferred_sub_location)
        or _normalize_runtime_text(resolve_result.get("sub_location"))
        or None
    )
    candidate_kind = lookup_candidate_kind or _runtime_location_candidate_kind(candidate_text or "")
    candidate_is_meaningful = bool(candidate_text and candidate_kind in LEDGER_LOCATION_SAFE_KINDS)
    attempts, last_kind = _location_attempt_state(session)
    last_user_text = _last_user_response_text(session)
    last_user_confirmation = _bare_confirmation_value(last_user_text)
    confirmed_by_caller = bool(
        candidate_is_meaningful and last_kind == "confirm_candidate" and last_user_confirmation == "yes"
    )

    if location_gate.get("confirmed"):
        followup_kind = None
        dead_end = False
    elif confirmed_by_caller:
        followup_kind = None
        dead_end = False
    elif candidate_is_meaningful:
        if last_kind == "confirm_candidate" and last_user_confirmation == "no":
            followup_kind = "ask_spell"
        elif last_kind == "ask_spell" and attempts >= 3:
            followup_kind = "ask_landmark"
        else:
            followup_kind = "confirm_candidate"
        dead_end = False
    elif note_text or sub_location or candidate_text:
        if attempts >= LOCATION_DEAD_END_ATTEMPTS and last_kind == "ask_landmark":
            followup_kind = None
            dead_end = True
        elif last_kind in {"ask_spell", "ask_exact_address"} and attempts >= 2:
            followup_kind = "ask_landmark"
            dead_end = False
        else:
            followup_kind = "ask_exact_address"
            dead_end = False
    else:
        if attempts >= 2:
            followup_kind = "ask_landmark"
        else:
            followup_kind = "ask_where"
        dead_end = False

    return {
        "candidate_text": candidate_text,
        "candidate_kind": candidate_kind if candidate_text else None,
        "location_note": note_text,
        "sub_location": sub_location,
        "followup_kind": followup_kind,
        "followup_prompt": _location_followup_prompt(
            followup_kind,
            candidate_text,
            candidate_source=candidate_source,
        ),
        "attempts": attempts,
        "dead_end": dead_end,
        "needs_confirmation": bool(candidate_is_meaningful and not confirmed_by_caller and not location_gate.get("confirmed")),
        "confirmed_by_caller": confirmed_by_caller,
        "candidate_source": candidate_source,
    }


def _run_and_record_auto_tool(
    recorder: SessionRecorder | None,
    *,
    name: str,
    args: dict[str, Any],
    result_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = utc_now()
    started_perf = time.perf_counter()
    result = dispatch_tool_call(name, args)
    if result_override:
        result = {**result, **result_override}
    elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
    _record_tool_result(
        recorder,
        name=name,
        args=args,
        result=result,
        started_at=started_at,
        elapsed_ms=elapsed_ms,
    )
    return result


def _record_auto_tool_if_changed(
    session: dict[str, Any],
    recorder: SessionRecorder | None,
    *,
    name: str,
    args: dict[str, Any],
    result: dict[str, Any],
) -> None:
    latest = _latest_tool_call(session, name)
    if latest and (latest.get("args") or {}) == args and (latest.get("result") or {}) == result:
        return
    _record_tool_result(
        recorder,
        name=name,
        args=args,
        result=result,
        started_at=utc_now(),
        elapsed_ms=0,
    )


def _auto_follow_location_resolution(session: dict[str, Any], recorder: SessionRecorder | None) -> None:
    resolve_call = _latest_tool_call(session, "resolve_location_note")
    location_candidate = None
    location_note = None
    sub_location = None

    if resolve_call:
        resolve_args = resolve_call.get("args") or {}
        resolve_result = resolve_call.get("result") or {}
        location_candidate = _normalize_runtime_text(
            resolve_result.get("anchor_location") or resolve_args.get("location_candidate")
        ) or None
        location_note = _normalize_runtime_text(
            resolve_result.get("normalized_note") or resolve_args.get("location_note")
        ) or None
        sub_location = _normalize_runtime_text(
            resolve_result.get("sub_location") or resolve_args.get("sub_location")
        ) or None
    else:
        location_candidate, location_note, sub_location = _infer_location_bundle_from_transcript(session)
        if location_candidate and (location_note or sub_location):
            resolve_args = {
                "location_candidate": location_candidate,
                "location_note": location_note or sub_location,
                "sub_location": sub_location,
            }
            if not _has_tool_call_for_query(session, ("resolve_location_note",), location_candidate):
                _run_and_record_auto_tool(recorder, name="resolve_location_note", args=resolve_args)
                session = get_session(recorder.session_id) if recorder else session

    if not location_candidate:
        return
    transcript = _combined_user_transcript(session)
    if not _has_emergency_context(transcript):
        return

    allowed, reason = assess_searchable_location_query(location_candidate)
    if not allowed:
        return
    if _has_tool_call_for_query(session, ("validate_address", "lookup_address"), location_candidate):
        return

    result_override = {
        "location_query_reason": reason,
        "requires_confirmation": reason not in AUTO_PIN_SAFE_LOCATION_REASONS,
        "candidate_only": reason not in AUTO_PIN_SAFE_LOCATION_REASONS,
    }
    lookup_result = _run_and_record_auto_tool(
        recorder,
        name="lookup_address",
        args={"address_text": location_candidate, "allow_best_effort": True},
        result_override=result_override,
    )
    if reason not in AUTO_PIN_SAFE_LOCATION_REASONS:
        return
    normalized_address = _normalize_runtime_text(lookup_result.get("normalized_address"))
    if not normalized_address:
        return


def _combined_user_transcript(session: dict[str, Any], *, count: int = 18) -> str:
    turns = session.get("client", {}).get("transcripts", {}).get("user", []) or []
    snippets = [_normalize_runtime_text(turn.get("text")) for turn in turns[-count:]]
    return _normalize_runtime_text(" ".join(item for item in snippets if item))


def _best_runtime_fact_text(session: dict[str, Any]) -> str:
    server = session.get("server") or {}
    enhancement = server.get("enhancement") or {}
    candidates = [
        _normalize_runtime_text(enhancement.get("clean_reconstruction")),
        _normalize_runtime_text(enhancement.get("raw_reconstruction")),
        _combined_user_transcript(session),
    ]
    best = max(candidates, key=lambda item: len(item or ""))
    return best or ""


def _shared_ledger(session: dict[str, Any]) -> dict[str, Any]:
    return normalize_shared_ledger(session.get("shared_ledger"))


def _patch_shared_ledger(recorder: SessionRecorder | None, ledger: dict[str, Any]) -> None:
    if recorder is None:
        return
    normalized = normalize_shared_ledger(ledger)
    recorder.patch_session(
        {
            "shared_ledger": normalized,
            "ledger_prompt_context": build_ledger_prompt_context(normalized),
        }
    )


def _apply_soft_ledger_update(
    session: dict[str, Any],
    recorder: SessionRecorder | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    ledger = _shared_ledger(session)
    soft_state = dict((result or {}).get("soft_state") or {})
    ledger["soft_state"]["people_count_best_guess"] = soft_state.get("people_count_best_guess")
    ledger["soft_state"]["caller_role"] = str(soft_state.get("caller_role") or "unknown")
    ledger["soft_state"]["notes"] = list(soft_state.get("notes") or [])
    ledger["version"] = int(ledger.get("version") or 0) + 1
    _patch_shared_ledger(recorder, ledger)
    return ledger


def _shared_ledger_tool_args(shared_ledger: dict[str, Any]) -> dict[str, Any]:
    hard_facts = normalize_shared_ledger(shared_ledger)["hard_facts"]
    return {
        "location_candidate": hard_facts.get("location_candidate"),
        "location_kind": hard_facts.get("location_kind"),
        "address_in_utterance": bool(hard_facts.get("address_in_utterance")),
        "location_note": hard_facts.get("location_note"),
        "sub_location": hard_facts.get("sub_location"),
        "inside_building": hard_facts.get("inside_building"),
        "issue_cues": list(hard_facts.get("issue_cues") or []),
        "victim_count": hard_facts.get("victim_count_confirmed", "unknown"),
        "child_present": hard_facts.get("child_present"),
        "bleeding_status": hard_facts.get("bleeding_status"),
        "breathing_status": hard_facts.get("breathing_status"),
        "consciousness_status": hard_facts.get("consciousness_status"),
        "trapped_status": hard_facts.get("trapped_status"),
    }


def _meaningful_location_kind(kind: str | None) -> bool:
    return str(kind or "none") in LEDGER_LOCATION_SAFE_KINDS


def _merge_shared_hard_facts(existing: dict[str, Any], incoming: dict[str, Any], *, lock_location: bool = False) -> dict[str, Any]:
    merged = dict(existing or {})
    existing_location = _normalize_runtime_text((existing or {}).get("location_candidate")) or None
    incoming_location = _normalize_runtime_text((incoming or {}).get("location_candidate")) or None
    existing_kind = str((existing or {}).get("location_kind") or "none")
    incoming_kind = str((incoming or {}).get("location_kind") or "none")
    existing_strength = LOCATION_KIND_STRENGTH.get(existing_kind, 0)
    incoming_strength = LOCATION_KIND_STRENGTH.get(incoming_kind, 0)

    if lock_location and existing_location:
        merged["location_candidate"] = existing_location
        merged["location_kind"] = existing_kind
        merged["address_in_utterance"] = bool(existing.get("address_in_utterance"))
    elif incoming_location and (
        not existing_location
        or incoming_strength >= existing_strength
        or incoming_location.casefold() == existing_location.casefold()
    ):
        merged["location_candidate"] = incoming_location
        merged["location_kind"] = incoming_kind
        merged["address_in_utterance"] = bool(incoming.get("address_in_utterance"))
    elif existing_location and (not incoming_location or incoming_kind in {"none", "vague"}):
        merged["location_candidate"] = existing_location
        merged["location_kind"] = existing_kind
        merged["address_in_utterance"] = bool(existing.get("address_in_utterance"))
    else:
        merged["location_candidate"] = incoming_location
        merged["location_kind"] = incoming_kind
        merged["address_in_utterance"] = bool(incoming.get("address_in_utterance"))

    for field_name in ("location_note", "sub_location"):
        if lock_location and existing_location:
            candidate = _normalize_runtime_text(existing.get(field_name)) or None
        else:
            candidate = _normalize_runtime_text(incoming.get(field_name)) or _normalize_runtime_text(existing.get(field_name)) or None
        merged[field_name] = candidate

    merged["inside_building"] = (
        incoming.get("inside_building")
        if incoming.get("inside_building") not in (None, "", "unknown")
        else existing.get("inside_building", "unknown")
    )
    merged["issue_cues"] = list(
        dict.fromkeys(list(existing.get("issue_cues") or []) + list(incoming.get("issue_cues") or []))
    )
    merged["victim_count_confirmed"] = (
        incoming.get("victim_count_confirmed")
        if incoming.get("victim_count_confirmed") not in (None, "", "unknown")
        else existing.get("victim_count_confirmed", "unknown")
    )
    for field_name in ("child_present", "bleeding_status", "breathing_status", "consciousness_status", "trapped_status"):
        merged[field_name] = (
            incoming.get(field_name)
            if incoming.get(field_name) not in (None, "", "unknown")
            else existing.get(field_name, "unknown")
        )
    return normalize_shared_ledger({"hard_facts": merged})["hard_facts"]


def _runtime_fallback_hard_facts(session: dict[str, Any]) -> dict[str, Any]:
    text = _best_runtime_fact_text(session)
    resolved: dict[str, Any] = {
        "location_candidate": None,
        "location_kind": "none",
        "address_in_utterance": False,
        "location_note": None,
        "sub_location": None,
        "inside_building": "unknown",
        "issue_cues": [],
        "victim_count_confirmed": "unknown",
        "child_present": "unknown",
        "bleeding_status": "unknown",
        "breathing_status": "unknown",
        "consciousness_status": "unknown",
        "trapped_status": "unknown",
    }
    if not text:
        return resolved

    lowered = text.casefold()
    candidate, note, sub_location = _infer_shared_ledger_location_bundle(session)
    text_candidate, text_note, text_sub_location = _infer_location_bundle_from_text(text)
    candidate = text_candidate or candidate
    note = text_note or note
    sub_location = text_sub_location or sub_location
    resolve_call = _latest_tool_call(session, "resolve_location_note")
    resolve_result = (resolve_call or {}).get("result") or {}
    anchor_location = _meaningful_runtime_location_candidate(resolve_result.get("anchor_location")) or candidate
    if anchor_location:
        resolved["location_candidate"] = anchor_location
        resolved["location_kind"] = _runtime_location_candidate_kind(anchor_location)
        resolved["address_in_utterance"] = resolved["location_kind"] in LEDGER_LOCATION_SAFE_KINDS
    resolved["location_note"] = (
        _normalize_runtime_text(resolve_result.get("normalized_note"))
        or _normalize_runtime_text(note)
        or None
    )
    resolved["sub_location"] = (
        _normalize_runtime_text(resolve_result.get("sub_location"))
        or _normalize_runtime_text(sub_location)
        or None
    )
    if any(word in lowered for word in ("building", "room", "shop", "inside", "entrance", "lobby", "floor")):
        resolved["inside_building"] = "yes"

    if _has_emergency_context(text):
        service_plan = dispatch_tool_call(
            "plan_response_services",
            {
                "transcript": text,
                "issue_type": None,
                "priority": None,
                "issue_cues": [],
            },
        )
        resolved["issue_cues"] = list(service_plan.get("issue_cues") or [])

    if any(word in lowered for word in ("daughter", "son", "child", "kid", "kids")):
        resolved["child_present"] = "yes"
        if "child_present" not in resolved["issue_cues"]:
            resolved["issue_cues"].append("child_present")

    if re.search(r"\b(?:no|not)\s+bleeding\b|\bno blood\b", lowered):
        resolved["bleeding_status"] = "no"
    elif any(word in lowered for word in ("bleeding", "blood", "nose is bleeding", "my nose is bleeding")):
        resolved["bleeding_status"] = "yes"

    if re.search(r"\b(?:not breathing|can't breathe|cannot breathe)\b", lowered):
        resolved["breathing_status"] = "no"
    elif re.search(r"\b(?:can breathe|breathing properly|able to breathe)\b", lowered):
        resolved["breathing_status"] = "yes"

    if re.search(r"\b(?:unconscious|not responding|unresponsive)\b", lowered):
        resolved["consciousness_status"] = "no"
    elif re.search(r"\b(?:awake|conscious|responsive)\b", lowered):
        resolved["consciousness_status"] = "yes"

    if re.search(r"\b(?:not trapped)\b", lowered):
        resolved["trapped_status"] = "no"
    elif re.search(r"\b(?:trapped|stuck|can't get out|cannot get out)\b", lowered):
        resolved["trapped_status"] = "yes"

    return normalize_shared_ledger({"hard_facts": resolved})["hard_facts"]


def _location_lock_active(ledger: dict[str, Any], location_followup: dict[str, Any] | None) -> bool:
    priority = ledger.get("priority") or {}
    gate = ledger.get("location_gate") or {}
    followup = location_followup or {}
    if gate.get("search_allowed") or gate.get("confirmed"):
        return False
    if followup.get("dead_end"):
        return False
    return bool(
        followup.get("followup_kind")
        or priority.get("location_followup_prompt")
        or gate.get("candidate_text")
        or (ledger.get("hard_facts") or {}).get("location_note")
    )


def _bare_confirmation_value(text: str | None) -> str | None:
    normalized = _normalize_runtime_text(text).strip(" .,!?:;").casefold()
    if normalized in {"yes", "yeah", "yep", "correct", "that's right", "thats right"}:
        return "yes"
    if normalized in {"no", "nope"}:
        return "no"
    return None


def _apply_runtime_confirmation_to_ledger(
    session: dict[str, Any],
    recorder: SessionRecorder | None,
) -> dict[str, Any]:
    ledger = _shared_ledger(session)
    user_turns = session.get("client", {}).get("transcripts", {}).get("user", []) or []
    last_runtime_turn_index = int((ledger.get("provenance") or {}).get("last_runtime_turn_index") or 0)
    next_question_field = (ledger.get("priority") or {}).get("next_question_field")
    if next_question_field == "location_candidate":
        changed = False
        followup = _build_location_followup_state(session, ledger)
        candidate_text = _normalize_runtime_text(followup.get("candidate_text")) or _normalize_runtime_text(
            (ledger.get("location_gate") or {}).get("candidate_text")
        )
        candidate_kind = str(
            followup.get("candidate_kind")
            or (ledger.get("location_gate") or {}).get("candidate_kind")
            or _runtime_location_candidate_kind(candidate_text)
            or "none"
        )
        for turn in user_turns[last_runtime_turn_index:]:
            value = _bare_confirmation_value(turn.get("text"))
            if value is None:
                continue
            if value == "yes" and candidate_text:
                ledger["hard_facts"]["location_candidate"] = candidate_text
                ledger["hard_facts"]["location_kind"] = candidate_kind
                ledger["hard_facts"]["address_in_utterance"] = candidate_kind in LEDGER_LOCATION_SAFE_KINDS
                ledger["location_gate"]["candidate_text"] = candidate_text
                ledger["location_gate"]["candidate_kind"] = candidate_kind
                ledger["location_gate"]["confirmed"] = True
                ledger["location_gate"]["search_allowed"] = True
                ledger["location_gate"]["needs_confirmation"] = False
                changed = True
            elif value == "no":
                ledger["location_gate"]["confirmed"] = False
                ledger["location_gate"]["needs_confirmation"] = False
                changed = True
        ledger["provenance"]["last_runtime_turn_index"] = len(user_turns)
        if changed:
            facts = shared_hard_facts_to_fact_ledger(ledger["hard_facts"])
            priority_flags = build_fact_priority_packet(facts, facts)["priority_flags"]
            ledger["priority"] = {
                **ledger["priority"],
                "missing_fields": list(priority_flags.get("missing_fields") or []),
                "next_question_field": priority_flags.get("next_question_field"),
                "next_question_goal": priority_flags.get("next_question_goal"),
                "question_style": priority_flags.get("question_style") or "short_open",
                "move_on_allowed": bool(priority_flags.get("move_on_allowed")),
            }
            ledger["version"] = int(ledger.get("version") or 0) + 1
            _patch_shared_ledger(recorder, ledger)
        return ledger
    if next_question_field not in LEDGER_BINARY_FIELDS:
        ledger["provenance"]["last_runtime_turn_index"] = len(user_turns)
        return ledger
    changed = False
    for turn in user_turns[last_runtime_turn_index:]:
        value = _bare_confirmation_value(turn.get("text"))
        if value is None:
            continue
        if ledger["hard_facts"].get(next_question_field) != value:
            ledger["hard_facts"][next_question_field] = value
            changed = True
    ledger["provenance"]["last_runtime_turn_index"] = len(user_turns)
    if changed:
        facts = shared_hard_facts_to_fact_ledger(ledger["hard_facts"])
        priority_flags = build_fact_priority_packet(facts, facts)["priority_flags"]
        ledger["priority"] = {
            **ledger["priority"],
            "missing_fields": list(priority_flags.get("missing_fields") or []),
            "next_question_field": priority_flags.get("next_question_field"),
            "next_question_goal": priority_flags.get("next_question_goal"),
            "question_style": priority_flags.get("question_style") or "short_open",
            "move_on_allowed": bool(priority_flags.get("move_on_allowed")),
        }
        ledger["version"] = int(ledger.get("version") or 0) + 1
        _patch_shared_ledger(recorder, ledger)
    return ledger


def _ledger_location_gate(
    shared_ledger: dict[str, Any],
    session: dict[str, Any],
    *,
    location_followup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = normalize_shared_ledger(shared_ledger)
    existing_gate = ledger.get("location_gate") or {}
    hard_facts = ledger["hard_facts"]
    facts = shared_hard_facts_to_fact_ledger(hard_facts)
    priority_flags = build_fact_priority_packet(facts, facts)["priority_flags"]
    lookup_call = _latest_tool_call(session, "lookup_address")
    validate_call = _latest_tool_call(session, "validate_address")
    nearby_call = _latest_tool_call(session, "nearby_context")
    lookup_result = lookup_call.get("result") if lookup_call else {}
    validate_result = validate_call.get("result") if validate_call else {}
    nearby_result = nearby_call.get("result") if nearby_call else {}
    followup = location_followup or {}
    lookup_reason = str((lookup_result or {}).get("location_query_reason") or "")
    validate_reason = str((validate_result or {}).get("location_query_reason") or "")
    exact_tool_match = bool(
        (
            lookup_result
            and not lookup_result.get("candidate_only")
            and lookup_result.get("lat") is not None
            and lookup_reason in {"exact_address", "explicit_address", "street_number"}
        )
        or (
            validate_result
            and not validate_result.get("candidate_only")
            and validate_result.get("lat") is not None
            and validate_reason in {"exact_address", "explicit_address", "street_number"}
        )
    )
    candidate_only = bool(
        (lookup_result or {}).get("candidate_only") or (validate_result or {}).get("candidate_only")
    )
    confirmed = bool(
        existing_gate.get("confirmed")
        or (
            followup.get("confirmed_by_caller")
            and followup.get("candidate_source") == "maps_candidate"
        )
        or exact_tool_match
    )
    candidate_text = _normalize_runtime_text(
        followup.get("candidate_text") or hard_facts.get("location_candidate")
    ) or None
    if _normalize_runtime_text(followup.get("candidate_text")):
        candidate_kind = followup.get("candidate_kind")
    elif _normalize_runtime_text(hard_facts.get("location_candidate")):
        candidate_kind = hard_facts.get("location_kind")
    else:
        candidate_kind = followup.get("candidate_kind")
    runtime_candidate_allowed = bool(
        candidate_text
        and candidate_kind in LEDGER_LOCATION_SAFE_KINDS
        and (followup.get("confirmed_by_caller") or existing_gate.get("confirmed"))
    )
    search_allowed = bool(priority_flags.get("location_search_allowed") or runtime_candidate_allowed)
    needs_confirmation = bool(
        followup.get("needs_confirmation")
        and not confirmed
        and candidate_text
    )

    if confirmed:
        search_reason = "confirmed_by_tools" if exact_tool_match else "caller_confirmed_runtime_candidate"
    elif priority_flags.get("location_search_allowed"):
        search_reason = "slm_meaningful_location"
    elif runtime_candidate_allowed:
        search_reason = "caller_confirmed_runtime_candidate"
    elif needs_confirmation and candidate_text:
        search_reason = "candidate_needs_confirmation"
    elif hard_facts.get("location_note") or hard_facts.get("sub_location"):
        search_reason = "best_effort_note_only"
    elif followup.get("location_note") or followup.get("sub_location"):
        search_reason = "best_effort_note_only"
    else:
        search_reason = "needs_more_location_detail"
    return {
        "search_allowed": search_allowed,
        "candidate_only": bool(
            candidate_only
            or (candidate_text and candidate_kind in LEDGER_LOCATION_SAFE_KINDS and not search_allowed)
        ),
        "confirmed": confirmed,
        "search_reason": search_reason,
        "candidate_text": candidate_text,
        "candidate_kind": candidate_kind,
        "needs_confirmation": needs_confirmation,
    }


def _refresh_shared_ledger_runtime(
    session: dict[str, Any],
    recorder: SessionRecorder | None,
) -> dict[str, Any]:
    ledger = _apply_runtime_confirmation_to_ledger(session, recorder)
    ledger = _shared_ledger(get_session(recorder.session_id) if recorder else session)
    runtime_fallback = _runtime_fallback_hard_facts(session)
    ledger["hard_facts"] = _merge_shared_hard_facts(
        ledger.get("hard_facts") or {},
        runtime_fallback,
        lock_location=bool((ledger.get("location_gate") or {}).get("confirmed")),
    )
    facts = shared_hard_facts_to_fact_ledger(ledger["hard_facts"])
    priority_flags = build_fact_priority_packet(facts, facts)["priority_flags"]
    ledger["priority"] = {
        "missing_fields": list(priority_flags.get("missing_fields") or []),
        "next_question_field": priority_flags.get("next_question_field"),
        "next_question_goal": priority_flags.get("next_question_goal"),
        "question_style": priority_flags.get("question_style") or "short_open",
        "move_on_allowed": bool(priority_flags.get("move_on_allowed")),
        "location_followup_kind": None,
        "location_followup_prompt": None,
        "location_dead_end": False,
        "location_attempts": 0,
        "location_lock_active": False,
    }

    tool_args = _shared_ledger_tool_args(ledger)
    _record_auto_tool_if_changed(
        session,
        recorder,
        name="checklist_by_incident",
        args=tool_args,
        result=dispatch_tool_call("checklist_by_incident", tool_args),
    )
    handoff_args = {
        **tool_args,
        "caller_summary": _combined_user_transcript(session) or None,
    }
    _record_auto_tool_if_changed(
        session,
        recorder,
        name="build_handoff_brief",
        args=handoff_args,
        result=dispatch_tool_call("build_handoff_brief", handoff_args),
    )

    inferred_candidate, inferred_note, inferred_sub_location = _infer_shared_ledger_location_bundle(session)
    resolve_candidate = _meaningful_runtime_location_candidate(tool_args.get("location_candidate")) or inferred_candidate
    resolve_note = (
        tool_args.get("location_note")
        or inferred_note
        or tool_args.get("sub_location")
        or inferred_sub_location
    )
    resolve_sub_location = tool_args.get("sub_location") or inferred_sub_location
    resolve_args = {
        "location_candidate": resolve_candidate,
        "location_note": resolve_note,
        "sub_location": resolve_sub_location,
    }
    if resolve_args.get("location_note"):
        latest_resolve = _latest_tool_call(session, "resolve_location_note")
        if (latest_resolve or {}).get("args") != resolve_args:
            _run_and_record_auto_tool(recorder, name="resolve_location_note", args=resolve_args)
            session = get_session(recorder.session_id) if recorder else session

    location_followup = _build_location_followup_state(session, ledger)
    ledger["location_gate"] = _ledger_location_gate(ledger, session, location_followup=location_followup)
    location_candidate = (
        _normalize_runtime_text(ledger["hard_facts"].get("location_candidate"))
        or _normalize_runtime_text((ledger.get("location_gate") or {}).get("candidate_text"))
        or None
    )
    def _apply_location_followup_priority(location_followup_state: dict[str, Any]) -> None:
        if location_followup_state.get("followup_kind") and not ledger["location_gate"]["search_allowed"]:
            location_lock_active = _location_lock_active(ledger, location_followup_state)
            ledger["priority"].update(
                {
                    "next_question_field": "location_candidate",
                    "next_question_goal": {
                        "ask_where": "ask where they are",
                        "ask_exact_address": "get the exact address",
                        "confirm_candidate": "confirm the location clue",
                        "ask_spell": "spell the location clue",
                        "ask_landmark": "get the nearest landmark and surroundings",
                    }.get(location_followup_state.get("followup_kind"), "pinpoint where they are"),
                    "question_style": "yes_no"
                    if location_followup_state.get("followup_kind") == "confirm_candidate"
                    else "short_open",
                    "move_on_allowed": bool(location_followup_state.get("dead_end") or priority_flags.get("move_on_allowed")),
                    "location_followup_kind": location_followup_state.get("followup_kind"),
                    "location_followup_prompt": location_followup_state.get("followup_prompt"),
                    "location_dead_end": bool(location_followup_state.get("dead_end")),
                    "location_attempts": int(location_followup_state.get("attempts") or 0),
                    "location_lock_active": location_lock_active,
                }
            )
        else:
            ledger["priority"].update(
                {
                    "location_followup_kind": location_followup_state.get("followup_kind"),
                    "location_followup_prompt": location_followup_state.get("followup_prompt"),
                    "location_dead_end": bool(location_followup_state.get("dead_end")),
                    "location_attempts": int(location_followup_state.get("attempts") or 0),
                    "location_lock_active": _location_lock_active(ledger, location_followup_state),
                }
            )

    _apply_location_followup_priority(location_followup)
    preflight_candidate = _meaningful_runtime_location_candidate(location_followup.get("candidate_text"))
    if (
        preflight_candidate
        and location_followup.get("needs_confirmation")
        and _has_emergency_context(_combined_user_transcript(session))
        and not _has_tool_call_for_query(session, ("lookup_address",), preflight_candidate)
    ):
        preflight_kind = classify_location_kind(preflight_candidate)
        _run_and_record_auto_tool(
            recorder,
            name="lookup_address",
            args={"address_text": preflight_candidate, "allow_best_effort": True},
            result_override={
                "location_query_reason": preflight_kind,
                "requires_confirmation": True,
                "candidate_only": True,
            },
        )
        session = get_session(recorder.session_id) if recorder else session
        location_followup = _build_location_followup_state(session, ledger)
        ledger["location_gate"] = _ledger_location_gate(ledger, session, location_followup=location_followup)
        _apply_location_followup_priority(location_followup)
    if ledger["location_gate"]["search_allowed"] and location_candidate and not location_followup.get("needs_confirmation"):
        latest_lookup = _latest_tool_call(session, "lookup_address")
        if not latest_lookup or _normalize_runtime_text((latest_lookup.get("args") or {}).get("address_text")) != location_candidate:
            location_kind = (
                ledger["hard_facts"].get("location_kind")
                if _normalize_runtime_text(ledger["hard_facts"].get("location_candidate"))
                else (ledger.get("location_gate") or {}).get("candidate_kind")
            )
            exact_like = str(location_kind or "none") == "exact_address"
            caller_confirmed = bool((ledger.get("location_gate") or {}).get("confirmed"))
            result_override = {
                "location_query_reason": location_kind,
                "requires_confirmation": not caller_confirmed and not exact_like,
                "candidate_only": not caller_confirmed and not exact_like,
            }
            _run_and_record_auto_tool(
                recorder,
                name="lookup_address",
                args={"address_text": location_candidate, "allow_best_effort": True},
                result_override=result_override,
            )
            session = get_session(recorder.session_id) if recorder else session
            location_followup = _build_location_followup_state(session, ledger)
            ledger["location_gate"] = _ledger_location_gate(ledger, session, location_followup=location_followup)

    previous = normalize_shared_ledger(session.get("shared_ledger"))
    next_ledger = normalize_shared_ledger({**ledger, "version": previous.get("version", 0)})
    if next_ledger != previous:
        next_ledger["version"] = int(previous.get("version") or 0) + 1
    else:
        next_ledger["version"] = int(previous.get("version") or 0)
    _patch_shared_ledger(recorder, next_ledger)
    return next_ledger


def _should_schedule_shared_ledger(session: dict[str, Any]) -> bool:
    ledger = _shared_ledger(session)
    user_turns = session.get("client", {}).get("transcripts", {}).get("user", []) or []
    start_index = int((ledger.get("provenance") or {}).get("last_slm_turn_index") or 0)
    if start_index >= len(user_turns):
        return False
    new_turns = user_turns[start_index:]
    substantive_count = 0
    for turn in new_turns:
        text = _normalize_runtime_text(turn.get("text"))
        if not text:
            continue
        if is_immediate_fact_ledger_trigger(text):
            return True
        if not is_trivial_caller_turn(text):
            substantive_count += 1
    return substantive_count >= 2


def _fact_ledger_endpoint(settings: Any) -> str:
    return f"{settings.triage_base_url.rstrip('/')}/chat/completions"


def _parse_fact_ledger_response(payload: dict[str, Any]) -> FactLedger:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("No choices returned from fact ledger model")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if part.get("type") == "text")
    content = _normalize_runtime_text(content)
    content = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.IGNORECASE)
    parsed = json.loads(content)
    return FactLedger.model_validate((parsed or {}).get("merged_facts") or {})


def _run_fact_ledger_inference(settings: Any, caller_turn: str, prior_facts: FactLedger) -> FactLedger:
    response = httpx.post(
        _fact_ledger_endpoint(settings),
        headers={
            "Authorization": f"Bearer {settings.triage_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _fact_ledger_model_id(settings),
            "messages": [
                {
                    "role": "system",
                    "content": FACT_LEDGER_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "caller_turn": caller_turn,
                            "prior_facts": prior_facts.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        },
        timeout=settings.triage_request_timeout_s,
    )
    response.raise_for_status()
    return _parse_fact_ledger_response(response.json())


async def _run_shared_ledger_job(session_id: str, settings: Any) -> None:
    recorder = SessionRecorder(session_id)
    registry_state = LEDGER_JOB_REGISTRY.setdefault(
        session_id,
        {"running": False, "dirty": False, "task": None, "last_user_turn_count": 0},
    )
    try:
        while True:
            session = get_session(session_id)
            ledger = _shared_ledger(session)
            ledger["provenance"]["slm_job_state"] = "analyzing"
            _patch_shared_ledger(recorder, ledger)
            user_turns = session.get("client", {}).get("transcripts", {}).get("user", []) or []
            caller_turn, substantive_turn_index = latest_substantive_caller_window(user_turns, limit=3)
            if not caller_turn:
                ledger["provenance"]["slm_job_state"] = "idle"
                _patch_shared_ledger(recorder, ledger)
                break
            prior_facts = shared_hard_facts_to_fact_ledger(ledger["hard_facts"])
            merged_facts = await asyncio.to_thread(_run_fact_ledger_inference, settings, caller_turn, prior_facts)
            session = get_session(session_id)
            next_ledger = _shared_ledger(session)
            incoming_hard_facts = fact_ledger_to_shared_hard_facts(merged_facts)
            next_ledger["hard_facts"] = _merge_shared_hard_facts(
                next_ledger["hard_facts"],
                incoming_hard_facts,
                lock_location=bool((next_ledger.get("location_gate") or {}).get("confirmed")),
            )
            next_ledger["provenance"]["last_slm_turn_index"] = max(substantive_turn_index, len(user_turns))
            next_ledger["provenance"]["last_slm_run_at"] = utc_now()
            next_ledger["provenance"]["slm_job_state"] = "idle"
            next_ledger["version"] = int(next_ledger.get("version") or 0) + 1
            _patch_shared_ledger(recorder, next_ledger)
            session = get_session(session_id)
            _refresh_shared_ledger_runtime(session, recorder)
            registry_state = LEDGER_JOB_REGISTRY.get(session_id) or registry_state
            if registry_state.get("dirty"):
                registry_state["dirty"] = False
                continue
            break
    except Exception as exc:
        session = get_session(session_id)
        ledger = _shared_ledger(session)
        ledger["hard_facts"] = _merge_shared_hard_facts(
            ledger.get("hard_facts") or {},
            _runtime_fallback_hard_facts(session),
            lock_location=bool((ledger.get("location_gate") or {}).get("confirmed")),
        )
        ledger["provenance"]["slm_job_state"] = "error"
        ledger["version"] = int(ledger.get("version") or 0) + 1
        _patch_shared_ledger(recorder, ledger)
        recorder.patch_server({"shared_ledger_error": str(exc)})
        session = get_session(session_id)
        _refresh_shared_ledger_runtime(session, recorder)
    finally:
        registry_state = LEDGER_JOB_REGISTRY.setdefault(
            session_id,
            {"running": False, "dirty": False, "task": None, "last_user_turn_count": 0},
        )
        registry_state["running"] = False
        registry_state["task"] = None


def _schedule_shared_ledger_refresh(session_id: str, settings: Any) -> None:
    session = get_session(session_id)
    if not _should_schedule_shared_ledger(session):
        return
    user_turn_count = len(session.get("client", {}).get("transcripts", {}).get("user", []) or [])
    registry_state = LEDGER_JOB_REGISTRY.setdefault(
        session_id,
        {"running": False, "dirty": False, "task": None, "last_user_turn_count": 0},
    )
    registry_state["last_user_turn_count"] = user_turn_count
    if registry_state.get("running"):
        registry_state["dirty"] = True
        return
    registry_state["running"] = True
    registry_state["dirty"] = False
    registry_state["task"] = asyncio.create_task(_run_shared_ledger_job(session_id, settings))


def _derive_dispatch_inputs(session: dict[str, Any]) -> dict[str, Any]:
    tool_calls = session.get("tool_calls") or []
    live_dispatch_mode = _resolve_live_dispatch_mode(
        (session.get("server") or {}).get("live_dispatch_mode") or (session.get("server") or {}).get("triage_engine")
    )
    shared_ledger = _shared_ledger(session)
    hard_facts = shared_ledger.get("hard_facts") or {}
    location_gate = shared_ledger.get("location_gate") or {}
    checklist_call = _latest_tool_call(session, "checklist_by_incident")
    ticket_call = _latest_tool_call(session, "create_incident_ticket")
    lookup_call = _latest_tool_call(session, "lookup_address")
    validate_call = _latest_tool_call(session, "validate_address")
    nearby_call = _latest_tool_call(session, "nearby_context")
    resolve_call = _latest_tool_call(session, "resolve_location_note")
    transcript = _combined_user_transcript(session)
    ticket_result = ticket_call.get("result") if ticket_call else {}
    checklist_args = checklist_call.get("args") if checklist_call else {}
    lookup_result = lookup_call.get("result") if lookup_call else {}
    validate_result = validate_call.get("result") if validate_call else {}
    nearby_result = nearby_call.get("result") if nearby_call else {}
    resolve_result = resolve_call.get("result") if resolve_call else {}
    ticket_address = _normalize_runtime_text(ticket_result.get("address"))
    if live_dispatch_mode == "slm" and not location_gate.get("confirmed"):
        ticket_address = None
    gated_hard_location = (
        _normalize_runtime_text(hard_facts.get("location_candidate"))
        if location_gate.get("search_allowed") or location_gate.get("confirmed")
        else None
    )
    gated_candidate_text = (
        _normalize_runtime_text(location_gate.get("candidate_text"))
        if location_gate.get("search_allowed") or location_gate.get("confirmed")
        else None
    )

    location_text = (
        ticket_address
        or _normalize_runtime_text(nearby_result.get("normalized_address"))
        or _normalize_runtime_text(
            None if validate_result.get("candidate_only") else validate_result.get("normalized_address")
        )
        or _normalize_runtime_text(
            None if lookup_result.get("candidate_only") else lookup_result.get("normalized_address")
        )
        or gated_hard_location
        or gated_candidate_text
        or _normalize_runtime_text(hard_facts.get("location_note"))
        or _normalize_runtime_text(resolve_result.get("anchor_location"))
        or _normalize_runtime_text(lookup_result.get("normalized_address"))
        or _normalize_runtime_text(validate_result.get("normalized_address"))
    )
    lat = (
        nearby_result.get("lat")
        or (None if validate_result.get("candidate_only") else validate_result.get("lat"))
        or (None if lookup_result.get("candidate_only") else lookup_result.get("lat"))
    )
    lon = (
        nearby_result.get("lon")
        or (None if validate_result.get("candidate_only") else validate_result.get("lon"))
        or (None if lookup_result.get("candidate_only") else lookup_result.get("lon"))
    )
    location_confirmed = bool(
        location_gate.get("confirmed")
        or lat is not None
        or (
            validate_result
            and not validate_result.get("candidate_only")
            and validate_result.get("lat") is not None
        )
        or (
            lookup_result
            and not lookup_result.get("candidate_only")
            and lookup_result.get("lat") is not None
        )
    )
    dispatch_location_text = (
        _normalize_runtime_text(nearby_result.get("normalized_address"))
        or _normalize_runtime_text(
            None if validate_result.get("candidate_only") else validate_result.get("normalized_address")
        )
        or _normalize_runtime_text(
            None if lookup_result.get("candidate_only") else lookup_result.get("normalized_address")
        )
        or (
            gated_hard_location
            if location_gate.get("confirmed")
            else None
        )
        or (
            gated_candidate_text
            if location_gate.get("confirmed")
            else None
        )
    )
    return {
        "transcript": transcript,
        "issue_type": ticket_result.get("issue_type"),
        "priority": ticket_result.get("priority"),
        "issue_cues": list(hard_facts.get("issue_cues") or checklist_args.get("issue_cues") or []),
        "location_text": location_text or None,
        "dispatch_location_text": dispatch_location_text or None,
        "lat": lat,
        "lon": lon,
        "location_confirmed": location_confirmed,
        "tool_calls": tool_calls,
    }


def _dispatch_state_changed(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    if not previous:
        return True
    previous_services = previous.get("services") or {}
    current_services = current.get("services") or {}
    if previous.get("human_monitoring") != current.get("human_monitoring"):
        return True
    if previous.get("summary") != current.get("summary"):
        return True
    if previous.get("announcement_line") != current.get("announcement_line"):
        return True
    if set(previous_services) != set(current_services):
        return True
    for name, current_item in current_services.items():
        previous_item = previous_services.get(name) or {}
        if (
            previous_item.get("status") != current_item.get("status")
            or previous_item.get("eta_text") != current_item.get("eta_text")
            or previous_item.get("location_confirmed") != current_item.get("location_confirmed")
            or previous_item.get("base_name") != current_item.get("base_name")
            or previous_item.get("base_address") != current_item.get("base_address")
            or previous_item.get("distance_km") != current_item.get("distance_km")
        ):
            return True
    return False


def _dispatch_prompt_context(dispatch_state: dict[str, Any], version: int) -> dict[str, Any]:
    services = dispatch_state.get("services") or {}
    summary_parts = [
        f"{service.get('label')} {service.get('status_label', '').lower()} ({service.get('eta_text')})"
        for service in services.values()
    ]
    return {
        "version": version,
        "human_monitoring": bool(dispatch_state.get("human_monitoring")),
        "monitor_name": dispatch_state.get("monitor_name"),
        "serious_emergency": bool(dispatch_state.get("serious_emergency")),
        "services_summary": " · ".join(summary_parts) if summary_parts else "No active service movement.",
        "announcement_line": dispatch_state.get("announcement_line"),
    }


def _maybe_auto_create_ticket(
    session: dict[str, Any],
    recorder: SessionRecorder | None,
    *,
    plan: dict[str, Any],
    dispatch_state: dict[str, Any],
    dispatch_inputs: dict[str, Any],
) -> None:
    live_dispatch_mode = _resolve_live_dispatch_mode(
        (session.get("server") or {}).get("live_dispatch_mode") or (session.get("server") or {}).get("triage_engine")
    )
    if _latest_tool_call(session, "create_incident_ticket"):
        return
    if not _has_emergency_context(dispatch_inputs.get("transcript")):
        return
    location_text = _normalize_runtime_text(
        dispatch_inputs.get("dispatch_location_text")
        if live_dispatch_mode == "slm"
        else dispatch_inputs.get("location_text")
    )
    if not location_text:
        return
    if live_dispatch_mode == "slm" and not dispatch_inputs.get("location_confirmed"):
        return
    if not dispatch_state.get("dispatchable"):
        return
    caller_summary = None
    handoff_call = _latest_tool_call(session, "build_handoff_brief")
    if handoff_call:
        handoff_result = handoff_call.get("result") or {}
        caller_summary = handoff_result.get("caller_summary") or handoff_result.get("one_line")
    caller_summary = caller_summary or dispatch_inputs.get("transcript") or "Emergency call in progress."
    service_names = plan.get("needed_services") or []
    notes = [f"service={name}" for name in service_names]
    if dispatch_state.get("human_monitoring"):
        notes.append(f"human_monitor={dispatch_state.get('monitor_name') or 'Alex'}")
    _run_and_record_auto_tool(
        recorder,
        name="create_incident_ticket",
        args={
            "caller_summary": caller_summary,
            "address": location_text,
            "issue_type": plan.get("issue_type") or "GENERAL",
            "priority": plan.get("priority") or "MEDIUM",
            "notes": notes,
        },
    )


def _auto_dispatch_services(session: dict[str, Any], recorder: SessionRecorder | None) -> dict[str, Any] | None:
    dispatch_inputs = _derive_dispatch_inputs(session)
    live_dispatch_mode = _resolve_live_dispatch_mode(
        (session.get("server") or {}).get("live_dispatch_mode") or (session.get("server") or {}).get("triage_engine")
    )
    if not dispatch_inputs.get("transcript"):
        return None
    if not (_has_emergency_context(dispatch_inputs.get("transcript")) or (dispatch_inputs.get("issue_cues") or [])):
        return None
    plan_args = {
        "transcript": dispatch_inputs.get("transcript"),
        "issue_type": dispatch_inputs.get("issue_type"),
        "priority": dispatch_inputs.get("priority"),
        "issue_cues": dispatch_inputs.get("issue_cues") or [],
    }
    plan = dispatch_tool_call("plan_response_services", plan_args)
    response_bases = dict((session.get("dispatch_services") or {}).get("response_bases") or {})
    lat = dispatch_inputs.get("lat")
    lon = dispatch_inputs.get("lon")
    if dispatch_inputs.get("location_confirmed") and lat is not None and lon is not None:
        if not response_bases or not _has_tool_call_for_coords(session, "lookup_response_bases", lat, lon):
            response_bases = _run_and_record_auto_tool(
                recorder,
                name="lookup_response_bases",
                args={
                    "lat": lat,
                    "lon": lon,
                    "location_text": dispatch_inputs.get("location_text"),
                },
            ).get("services", {})
            session = get_session(recorder.session_id) if recorder else session
    previous_state = session.get("dispatch_services") or {}
    dispatch_args = {
        "session_id": session.get("session_id") or "",
        "plan": plan,
        "location_text": dispatch_inputs.get("dispatch_location_text")
        if live_dispatch_mode == "slm"
        else dispatch_inputs.get("location_text"),
        "location_confirmed": bool(dispatch_inputs.get("location_confirmed")),
        "response_bases": response_bases,
        "prior_state": previous_state,
        "now_iso": utc_now(),
    }
    dispatch_state = dispatch_tool_call("simulate_dispatch_services", dispatch_args)
    _record_auto_tool_if_changed(session, recorder, name="plan_response_services", args=plan_args, result=plan)
    _record_auto_tool_if_changed(session, recorder, name="simulate_dispatch_services", args=dispatch_args, result=dispatch_state)

    _maybe_auto_create_ticket(session, recorder, plan=plan, dispatch_state=dispatch_state, dispatch_inputs=dispatch_inputs)
    session = get_session(recorder.session_id) if recorder else session
    previous_state = session.get("dispatch_services") or {}
    changed = _dispatch_state_changed(previous_state, dispatch_state)
    version = int(previous_state.get("version") or 0)
    if changed:
        version += 1
    dispatch_state["version"] = version
    prompt_context = _dispatch_prompt_context(dispatch_state, version)
    if changed and recorder is not None:
        recorder.patch_session(
            {
                "dispatch_services": dispatch_state,
                "dispatch_prompt_context": prompt_context,
            }
        )
    elif not session.get("dispatch_prompt_context"):
        if recorder is not None:
            recorder.patch_session(
                {
                    "dispatch_services": dispatch_state,
                    "dispatch_prompt_context": prompt_context,
                }
            )
    return {
        "version": version,
        "prompt_context": prompt_context,
    }


async def _websocket_session_ai_coustics(websocket: WebSocket) -> None:
    settings = _ensure_llm_ready()
    enhancer = make_enhancer(settings)
    recorder: SessionRecorder | None = None
    interrupt_count = 0
    latest_triage_context: dict[str, Any] | None = None
    latest_ledger_context: dict[str, Any] | None = None
    latest_dispatch_context: dict[str, Any] | None = None
    raw_pcm = bytearray()
    clean_pcm = bytearray()
    enhancement_mode = "enhanced"
    enhancement_fallback_reason: str | None = None
    human_takeover_active = False
    handoff_recovery_prompt: str | None = None

    async def on_tool_call(tool_handle) -> None:
        nonlocal latest_ledger_context, latest_dispatch_context
        started_at = utc_now()
        started_perf = time.perf_counter()
        try:
            if live_dispatch_mode == "slm" and tool_handle.name in {
                "validate_address",
                "lookup_address",
                "lookup_response_bases",
            }:
                current_session = get_session(recorder.session_id) if recorder else {}
                location_gate = (_shared_ledger(current_session).get("location_gate") or {})
                if not location_gate.get("search_allowed"):
                    result = {
                        "blocked": True,
                        "reason": "location_search_not_allowed",
                        "message": "Location search is blocked until the shared ledger confirms a meaningful clue.",
                    }
                else:
                    result = dispatch_tool_call(tool_handle.name, tool_handle.args)
            else:
                result = dispatch_tool_call(tool_handle.name, tool_handle.args)
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            _record_tool_result(
                recorder,
                name=tool_handle.name,
                args=tool_handle.args,
                result=result,
                started_at=started_at,
                elapsed_ms=elapsed_ms,
            )
            if live_dispatch_mode == "slm" and tool_handle.name == "update_soft_ledger":
                current_session = get_session(recorder.session_id) if recorder else {}
                _apply_soft_ledger_update(current_session, recorder, result)
            if live_dispatch_mode == "slm" and tool_handle.name in {
                "update_soft_ledger",
                "resolve_location_note",
                "checklist_by_incident",
                "build_handoff_brief",
                "validate_address",
                "lookup_address",
                "lookup_response_bases",
            }:
                current_session = get_session(recorder.session_id) if recorder else {}
                _refresh_shared_ledger_runtime(current_session, recorder)
                current_session = get_session(recorder.session_id) if recorder else current_session
                _auto_dispatch_services(current_session, recorder)
                current_session = get_session(recorder.session_id) if recorder else current_session
                latest_ledger_context = current_session.get("ledger_prompt_context") or latest_ledger_context
                latest_dispatch_context = current_session.get("dispatch_prompt_context") or latest_dispatch_context
                if latest_ledger_context or latest_dispatch_context:
                    config = build_session_config(
                        live_dispatch_mode=live_dispatch_mode,
                        interrupt_count=interrupt_count,
                        interruption_recovery=False,
                        triage_context=None,
                        ledger_context=latest_ledger_context if live_dispatch_mode == "slm" else None,
                        dispatch_context=latest_dispatch_context,
                        human_takeover_active=human_takeover_active,
                        handoff_recovery_prompt=handoff_recovery_prompt,
                    )
                    await input_handle.send_config(config)
                    recorder.append_session_list(
                        "llm_prompt_snapshots",
                        {
                            "at": utc_now(),
                            "reason": f"tool:{tool_handle.name}",
                            "interrupt_count": interrupt_count,
                            "interruption_recovery": False,
                            "flush_duration_s": config.flush_duration_s,
                            "silence_timeout_s": config.silence_timeout_s,
                            "triage_version": None,
                            "ledger_version": latest_ledger_context.get("version") if latest_ledger_context else None,
                            "dispatch_version": latest_dispatch_context.get("version") if latest_dispatch_context else None,
                            "selected_engine": live_dispatch_mode,
                            "runtime_provider": "pioneer" if live_dispatch_mode == "slm" else "gradium",
                            "instructions": config.instructions,
                            "live_dispatch_mode": live_dispatch_mode,
                        },
                    )
            await tool_handle.send_json(result)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            _record_tool_result(
                recorder,
                name=tool_handle.name,
                args=tool_handle.args,
                error=str(exc),
                started_at=started_at,
                elapsed_ms=elapsed_ms,
            )
            raise

    await websocket.accept()
    start_msg = await websocket.receive_json()
    if start_msg.get("type") != "start":
        await websocket.close(code=4000, reason="Expected start message")
        return

    live_dispatch_mode = _resolve_live_dispatch_mode(
        start_msg.get("triage_mode") or (start_msg.get("client") or {}).get("triage_mode")
    )
    live_triage_settings = _ensure_live_runtime_ready_ws(live_dispatch_mode)
    session_id = start_msg.get("session_id") or f"session-{utc_now().replace(':', '-')}"
    recorder = SessionRecorder(session_id)
    clear_live_audio_window(session_id)
    initial_config = build_session_config(live_dispatch_mode=live_dispatch_mode)
    recorder.patch_server(
        {
            "status": "started",
            "started_at": utc_now(),
            "llm_model": settings.openai_model,
            "client_metadata": start_msg.get("client", {}),
            "mode": "live_ai_coustics",
            "triage_engine": live_dispatch_mode,
            "live_dispatch_mode": live_dispatch_mode,
            "adaptive_policy": {
                "interrupt_count": 0,
                "flush_duration_s": initial_config.flush_duration_s,
                "silence_timeout_s": initial_config.silence_timeout_s,
            },
            "enhancement": {
                "status": "live",
                "ai_coustics_model_id": settings.ai_coustics_model_id,
                "live_input_source": "enhanced",
                "parallel_enhancement": True,
                "fallback_to_raw": False,
            },
        }
    )
    recorder.append_session_list(
        "llm_prompt_snapshots",
        {
            "at": utc_now(),
            "reason": "session_start",
            "interrupt_count": 0,
            "interruption_recovery": False,
            "flush_duration_s": initial_config.flush_duration_s,
            "silence_timeout_s": initial_config.silence_timeout_s,
            "triage_version": None,
            "ledger_version": None,
            "selected_engine": None,
            "runtime_provider": None,
            "live_dispatch_mode": live_dispatch_mode,
            "instructions": initial_config.instructions,
        },
    )

    input_handle, output_handle = await gradbot.run(
        **_run_kwargs(),
        session_config=initial_config,
        input_format=gradbot.AudioFormat.Pcm,
        output_format=gradbot.AudioFormat.Pcm,
    )

    stop_event = asyncio.Event()
    pending_tool_tasks: set[asyncio.Task] = set()

    async def input_loop() -> None:
        nonlocal interrupt_count, latest_triage_context, latest_ledger_context, latest_dispatch_context, enhancement_mode, enhancement_fallback_reason, human_takeover_active, handoff_recovery_prompt
        while not stop_event.is_set():
            try:
                raw = await websocket.receive()
                if "bytes" in raw:
                    pcm_bytes = raw["bytes"]
                    if not pcm_bytes:
                        continue
                    raw_pcm.extend(pcm_bytes)
                    live_bytes = pcm_bytes
                    clean_bytes = b""
                    try:
                        clean_bytes = enhancer.process_bytes(pcm_bytes)
                        if clean_bytes:
                            clean_pcm.extend(clean_bytes)
                            if enhancement_mode == "enhanced":
                                live_bytes = clean_bytes
                    except Exception as exc:
                        enhancement_mode = "raw_fallback"
                        enhancement_fallback_reason = str(exc)
                        recorder.patch_server(
                            {
                                "enhancement": {
                                    "status": "degraded",
                                    "live_input_source": "raw_fallback",
                                    "fallback_to_raw": True,
                                    "fallback_reason": enhancement_fallback_reason,
                                }
                            }
                        )
                    append_live_audio_window(session_id, pcm_bytes, clean_bytes)
                    await input_handle.send_audio(live_bytes)
                    continue

                if "text" not in raw:
                    continue

                data = json.loads(raw["text"])
                msg_type = data.get("type")
                if msg_type == "config":
                    reason = data.get("reason")
                    recovery = bool(data.get("interruption_recovery"))
                    human_takeover_active = bool(data.get("human_takeover_active"))
                    handoff_recovery_prompt = data.get("handoff_recovery_prompt")
                    if live_dispatch_mode == "slm" and isinstance(data.get("triage_context"), dict):
                        latest_triage_context = data.get("triage_context")
                    if live_dispatch_mode == "slm" and isinstance(data.get("ledger_context"), dict):
                        latest_ledger_context = data.get("ledger_context")
                    if isinstance(data.get("dispatch_context"), dict):
                        latest_dispatch_context = data.get("dispatch_context")
                    interrupt_count = max(0, int(data.get("interrupt_count") or 0))
                    config = build_session_config(
                        live_dispatch_mode=live_dispatch_mode,
                        interrupt_count=interrupt_count,
                        interruption_recovery=recovery,
                        triage_context=latest_triage_context if live_dispatch_mode == "slm" else None,
                        ledger_context=latest_ledger_context if live_dispatch_mode == "slm" else None,
                        dispatch_context=latest_dispatch_context,
                        human_takeover_active=human_takeover_active,
                        handoff_recovery_prompt=handoff_recovery_prompt,
                    )
                    await input_handle.send_config(config)
                    recorder.patch_server(
                        {
                            "adaptive_policy": {
                                "interrupt_count": interrupt_count,
                                "last_reason": reason,
                                "interruption_recovery": recovery,
                                "flush_duration_s": config.flush_duration_s,
                                "silence_timeout_s": config.silence_timeout_s,
                            }
                        },
                    )
                    recorder.append_session_list(
                        "llm_prompt_snapshots",
                        {
                            "at": utc_now(),
                            "reason": reason,
                            "interrupt_count": interrupt_count,
                            "interruption_recovery": recovery,
                            "flush_duration_s": config.flush_duration_s,
                            "silence_timeout_s": config.silence_timeout_s,
                            "triage_version": latest_triage_context.get("version") if latest_triage_context else None,
                            "ledger_version": latest_ledger_context.get("version") if latest_ledger_context else None,
                            "dispatch_version": latest_dispatch_context.get("version") if latest_dispatch_context else None,
                            "selected_engine": latest_ledger_context.get("selected_engine")
                            if latest_ledger_context
                            else (latest_triage_context.get("selected_engine") if latest_triage_context else live_dispatch_mode),
                            "runtime_provider": latest_ledger_context.get("runtime_provider")
                            if latest_ledger_context
                            else (latest_triage_context.get("runtime_provider") if latest_triage_context else ("gradium" if live_dispatch_mode == "llm_only" else None)),
                            "instructions": config.instructions,
                            "live_dispatch_mode": live_dispatch_mode,
                            "human_takeover_active": human_takeover_active,
                            "handoff_recovery_prompt": handoff_recovery_prompt,
                        },
                    )
                    if latest_ledger_context is not None:
                        recorder.patch_server(
                            {
                                "ledger_prompt": {
                                    "version": latest_ledger_context.get("version"),
                                    "missing_fields": latest_ledger_context.get("missing_fields"),
                                    "next_question_goal": latest_ledger_context.get("next_question_goal"),
                                    "location_search_allowed": latest_ledger_context.get("location_search_allowed"),
                                }
                            }
                        )
                    if latest_triage_context is not None:
                        recorder.patch_server(
                            {
                                "triage_prompt": {
                                    "version": latest_triage_context.get("version"),
                                    "selected_engine": latest_triage_context.get("selected_engine"),
                                    "runtime_provider": latest_triage_context.get("runtime_provider"),
                                    "missing_or_unknown_fields": latest_triage_context.get("missing_or_unknown_fields"),
                                    "dispatchable": latest_triage_context.get("dispatchable"),
                                    "autonomy_allowed": latest_triage_context.get("autonomy_allowed"),
                                }
                            }
                        )
                    continue
                if msg_type == "stop":
                    tail_bytes = b""
                    if enhancement_mode == "enhanced":
                        try:
                            tail_bytes = enhancer.flush()
                        except Exception as exc:
                            enhancement_mode = "raw_fallback"
                            enhancement_fallback_reason = str(exc)
                            recorder.patch_server(
                                {
                                    "enhancement": {
                                        "status": "degraded",
                                        "live_input_source": "raw_fallback",
                                        "fallback_to_raw": True,
                                        "fallback_reason": enhancement_fallback_reason,
                                    }
                                }
                            )
                    if tail_bytes:
                        clean_pcm.extend(tail_bytes)
                        append_live_audio_window(session_id, b"", tail_bytes)
                        await input_handle.send_audio(tail_bytes)
                    stop_event.set()
                    await input_handle.close()
                    break
            except Exception:
                stop_event.set()
                await input_handle.close()
                break

    async def output_loop() -> None:
        while not stop_event.is_set():
            msg = await output_handle.receive()
            if msg is None:
                break
            if msg.msg_type == "tool_call":
                handle = gradbot.websocket.ToolHandle(msg.tool_call_handle, msg.tool_call)

                async def _safe_tool_call(tool_handle=handle):
                    await on_tool_call(tool_handle)

                task = asyncio.create_task(_safe_tool_call())
                pending_tool_tasks.add(task)
                task.add_done_callback(pending_tool_tasks.discard)
                continue

            schema = gradbot.schemas.from_msg(msg)
            if schema is not None:
                await websocket.send_json(schema.model_dump())
            if msg.msg_type == "audio":
                if human_takeover_active:
                    continue
                await websocket.send_bytes(msg.data)

    try:
        await asyncio.gather(output_loop(), input_loop(), return_exceptions=True)
        if pending_tool_tasks:
            await asyncio.gather(*pending_tool_tasks, return_exceptions=True)

        recorder.patch_server(
            {
                "status": "processing_artifacts",
                "ended_at": utc_now(),
                "enhancement": {
                    "status": "processing_reconstructions",
                    "live_input_source": enhancement_mode,
                    "fallback_to_raw": enhancement_mode != "enhanced",
                    "fallback_reason": enhancement_fallback_reason,
                },
            }
        )
        artifacts = await finalize_audio_artifacts(
            session_id=session_id,
            raw_pcm=bytes(raw_pcm),
            clean_pcm=bytes(clean_pcm),
            settings=settings,
        )
        recorder.patch_server(
            {
                "status": "completed",
                "ended_at": utc_now(),
                "enhancement": {
                    "status": "completed",
                    "live_input_source": enhancement_mode,
                    "fallback_to_raw": enhancement_mode != "enhanced",
                    "fallback_reason": enhancement_fallback_reason,
                    **artifacts,
                },
            }
        )
    except Exception as exc:
        recorder.patch_server(
            {
                "status": "error",
                "ended_at": utc_now(),
                "error": str(exc),
                "enhancement": {
                    "status": "error",
                },
            }
        )
        raise
    finally:
        clear_live_audio_window(session_id)
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws")
async def websocket_session(websocket: WebSocket) -> None:
    await _websocket_session_ai_coustics(websocket)


@app.websocket("/ws-enhanced")
async def websocket_session_enhanced(websocket: WebSocket) -> None:
    await _websocket_session_ai_coustics(websocket)
