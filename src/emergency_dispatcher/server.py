from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import gradbot
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
    "road_designator",
    "street_number",
    "street_name_suffix",
    "street_name",
    "mixed_named_location",
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


def _live_triage_missing(settings) -> list[str]:
    missing: list[str] = []
    if not settings.triage_api_key:
        missing.append("TRIAGE_API_KEY")
    if not settings.triage_decoder_model:
        missing.append("TRIAGE_DECODER_MODEL")
    if not settings.triage_gliner_model:
        missing.append("TRIAGE_GLINER_MODEL")
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
    triage_update = analyze_session_triage(session, triage_settings)
    if triage_update is not None:
        recorder.patch_session(triage_session_patch(session, triage_update))
        session = get_session(session_id)
        dispatch_update = _auto_dispatch_services(session, recorder)
        return {
            "status": "ok",
            "triage_update": triage_update.model_dump(),
            "dispatch_update": dispatch_update,
            "stt_rescue_event": stt_rescue_event.model_dump() if stt_rescue_event else None,
        }
    latest_meta = session.get("triage_meta") or {}
    latest_turns = session.get("triage_turns") or []
    latest_turn = latest_turns[-1] if latest_turns else None
    dispatch_update = _auto_dispatch_services(session, recorder)
    return {
        "status": "ok",
        "triage_update": latest_turn,
        "dispatch_update": dispatch_update,
        "triage_meta": latest_meta,
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


def _infer_location_bundle_from_transcript(session: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    turns = session.get("client", {}).get("transcripts", {}).get("user", []) or []
    snippets = [_normalize_runtime_text(turn.get("text")) for turn in turns if _normalize_runtime_text(turn.get("text"))]
    combined = " ".join(snippets[-16:])
    if not combined:
        return None, None, None

    sub_location_match = AUTO_SUB_LOCATION_PATTERN.search(combined)
    sub_location = _normalize_runtime_text(sub_location_match.group(1)) if sub_location_match else None

    address = extract_address_candidate(combined)
    if address:
        return _normalize_runtime_text(address), sub_location, sub_location

    matches = list(AUTO_LOCATION_HINT_PATTERN.finditer(combined))
    for match in reversed(matches):
        candidate = _normalize_runtime_text(match.group(1))
        if not candidate:
            continue
        if sub_location and sub_location.casefold() in candidate.casefold():
            candidate = _normalize_runtime_text(re.sub(re.escape(sub_location), "", candidate, flags=re.IGNORECASE))
        candidate = re.split(r"\b(?:and|but|only|except|with)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.")
        allowed, _reason = assess_searchable_location_query(candidate)
        if allowed or len(candidate.split()) >= 2:
            return candidate or None, sub_location, sub_location
    return None, sub_location, sub_location


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
        "requires_confirmation": reason == "named_place",
        "candidate_only": reason == "named_place",
    }
    lookup_result = _run_and_record_auto_tool(
        recorder,
        name="lookup_address",
        args={"address_text": location_candidate},
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


def _derive_dispatch_inputs(session: dict[str, Any]) -> dict[str, Any]:
    tool_calls = session.get("tool_calls") or []
    checklist_call = _latest_tool_call(session, "checklist_by_incident")
    ticket_call = _latest_tool_call(session, "create_incident_ticket")
    lookup_call = _latest_tool_call(session, "lookup_address")
    validate_call = _latest_tool_call(session, "validate_address")
    nearby_call = _latest_tool_call(session, "nearby_context")
    resolve_call = _latest_tool_call(session, "resolve_location_note")
    merged = session.get("merged_triage_state") or {}
    transcript = _combined_user_transcript(session)
    ticket_result = ticket_call.get("result") if ticket_call else {}
    checklist_args = checklist_call.get("args") if checklist_call else {}
    lookup_result = lookup_call.get("result") if lookup_call else {}
    validate_result = validate_call.get("result") if validate_call else {}
    nearby_result = nearby_call.get("result") if nearby_call else {}
    resolve_result = resolve_call.get("result") if resolve_call else {}

    location_text = (
        _normalize_runtime_text(ticket_result.get("address"))
        or _normalize_runtime_text(nearby_result.get("normalized_address"))
        or _normalize_runtime_text(
            None if validate_result.get("candidate_only") else validate_result.get("normalized_address")
        )
        or _normalize_runtime_text(
            None if lookup_result.get("candidate_only") else lookup_result.get("normalized_address")
        )
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
        lat is not None
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
    return {
        "transcript": transcript,
        "issue_type": ticket_result.get("issue_type") or merged.get("issue_type"),
        "priority": ticket_result.get("priority") or merged.get("priority"),
        "issue_cues": list(checklist_args.get("issue_cues") or []),
        "location_text": location_text or None,
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
    if _latest_tool_call(session, "create_incident_ticket"):
        return
    if not _has_emergency_context(dispatch_inputs.get("transcript")):
        return
    location_text = _normalize_runtime_text(dispatch_inputs.get("location_text"))
    if not location_text:
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
    if not dispatch_inputs.get("transcript"):
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
        "location_text": dispatch_inputs.get("location_text"),
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
    latest_dispatch_context: dict[str, Any] | None = None
    raw_pcm = bytearray()
    clean_pcm = bytearray()
    enhancement_mode = "enhanced"
    enhancement_fallback_reason: str | None = None

    async def on_tool_call(tool_handle) -> None:
        started_at = utc_now()
        started_perf = time.perf_counter()
        try:
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
    initial_config = build_session_config()
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
        nonlocal interrupt_count, latest_triage_context, latest_dispatch_context, enhancement_mode, enhancement_fallback_reason
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
                    if live_dispatch_mode == "slm" and isinstance(data.get("triage_context"), dict):
                        latest_triage_context = data.get("triage_context")
                    if isinstance(data.get("dispatch_context"), dict):
                        latest_dispatch_context = data.get("dispatch_context")
                    interrupt_count = max(0, int(data.get("interrupt_count") or 0))
                    config = build_session_config(
                        interrupt_count=interrupt_count,
                        interruption_recovery=recovery,
                        triage_context=latest_triage_context if live_dispatch_mode == "slm" else None,
                        dispatch_context=latest_dispatch_context,
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
                            "dispatch_version": latest_dispatch_context.get("version") if latest_dispatch_context else None,
                            "selected_engine": latest_triage_context.get("selected_engine") if latest_triage_context else live_dispatch_mode,
                            "runtime_provider": latest_triage_context.get("runtime_provider") if latest_triage_context else ("gradium" if live_dispatch_mode == "llm_only" else None),
                            "instructions": config.instructions,
                            "live_dispatch_mode": live_dispatch_mode,
                        },
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
