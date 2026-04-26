import uuid

from fastapi.testclient import TestClient

from emergency_dispatcher import server
from emergency_dispatcher.server import app
from emergency_dispatcher.settings import get_settings
from emergency_dispatcher.stt_rescue import RescueCandidate
from emergency_dispatcher.stt_rescue import STTRescueEvent


client = TestClient(app)


def test_session_report_returns_triage_update(monkeypatch):
    server_settings = get_settings().model_copy(update={"triage_engine": "heuristic"})
    monkeypatch.setattr(server, "_ensure_live_triage_ready_http", lambda: server_settings)
    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "I am stuck at Delta Campus and my partner is bleeding."}
                ],
                "agent": [],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["triage_update"]["merged_triage_state"]["location"] == "Delta Campus"
    assert payload["triage_update"]["prompt_context"]["merged_triage_state"]["victim_bleeding"] == "yes"


def test_session_report_includes_stt_rescue_event(monkeypatch):
    monkeypatch.setattr(
        server,
        "_ensure_live_triage_ready_http",
        lambda: get_settings().model_copy(update={"triage_engine": "heuristic"}),
    )

    async def fake_rescue(*, session_id, session, settings):
        return STTRescueEvent(
            user_index=0,
            suspicious_reasons=["unlikely_phrase_be_the_child"],
            primary_transcript="I'm trying to be the child.",
            selected_provider="deepgram",
            selected_transcript="I'm trying to reach the child.",
            corrected_transcript="I'm trying to reach the child.",
            ask_for_repeat=True,
            location_needs_spelling=False,
            clip_source="clean",
            clip_path="runs/audio/fake.wav",
            candidates=[
                RescueCandidate(provider="deepgram", transcript="I'm trying to reach the child.", score=9.0, usable=True),
            ],
        )

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "I'm trying to be the child."}
                ],
                "agent": [],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stt_rescue_event"]["selected_provider"] == "deepgram"
    assert payload["triage_update"]["prompt_context"]["stt_rescue"]["corrected_transcript"] == "I'm trying to reach the child."


def test_session_report_can_bypass_live_triage(monkeypatch):
    async def fake_rescue(**kwargs):
        return STTRescueEvent(
            user_index=0,
            suspicious_reasons=[],
            primary_transcript="Can you hear me?",
            selected_provider="deepgram",
            selected_transcript="Can you hear me?",
            corrected_transcript="Can you hear me?",
            ask_for_repeat=False,
            location_needs_spelling=False,
            clip_source="clean",
            clip_path="runs/audio/fake.wav",
            continuous_compare=True,
            shadow_active=True,
            shadow_elapsed_s=0.42,
            active_provider="gradium",
            provider_scores={"gradium": 1.0, "deepgram": 1.4},
            candidates=[
                RescueCandidate(provider="deepgram", transcript="Can you hear me?", score=1.4, usable=True),
            ],
        )

    monkeypatch.setattr(
        server,
        "maybe_run_stt_rescue",
        fake_rescue,
    )
    monkeypatch.setattr(server, "analyze_session_triage", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("triage should not run in llm_only mode")))

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "triage_mode": "llm_only",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "Can you hear me?"}
                ],
                "agent": [],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["triage_enabled"] is False
    assert payload["triage_update"] is None
    assert payload["stt_rescue_event"]["selected_provider"] == "deepgram"
    assert payload["stt_rescue_meta"]["continuous_compare"] is True
    assert payload["triage_meta"]["selected_engine"] == "llm_only"


def test_session_report_llm_only_auto_attempts_searchable_place_but_marks_candidate_only(monkeypatch):
    async def fake_rescue(**kwargs):
        return None

    original_dispatch_tool_call = server.dispatch_tool_call

    def fake_dispatch_tool_call(name, args):
        if name == "resolve_location_note":
            return {
                "note_type": "sub_location",
                "normalized_note": "fourth floor",
                "anchor_location": "Delta campus",
                "sub_location": "fourth floor",
                "location_status": "usable_place",
                "usable_for_dispatch": True,
                "move_on_allowed": True,
                "search_allowed": True,
                "needs_confirmation": False,
                "reason": "anchored_note",
            }
        if name == "lookup_address":
            return {
                "found": True,
                "geocoded": True,
                "normalized_address": "Donaustraße 44, 12043 Berlin, Germany",
                "lat": 52.4799,
                "lon": 13.4394,
                "source": "google_geocoding",
                "confidence": "high",
                "reason": "google_match",
            }
        return original_dispatch_tool_call(name, args)

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "dispatch_tool_call", fake_dispatch_tool_call)
    monkeypatch.setattr(server, "analyze_session_triage", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("triage should not run in llm_only mode")))

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "triage_mode": "llm_only",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "I am on Delta campus, fourth floor."}
                ],
                "agent": [],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    session = server.get_session(session_id)
    tool_names = [tool["name"] for tool in session.get("tool_calls", [])]
    assert "resolve_location_note" in tool_names
    assert "lookup_address" not in tool_names


def test_session_report_llm_only_generates_dispatch_services_and_monitoring(monkeypatch):
    async def fake_rescue(**kwargs):
        return None

    original_dispatch_tool_call = server.dispatch_tool_call

    def fake_dispatch_tool_call(name, args):
        if name == "resolve_location_note":
            return {
                "note_type": "sub_location",
                "normalized_note": "fourth floor",
                "anchor_location": "Delta campus",
                "sub_location": "fourth floor",
                "location_status": "usable_place",
                "usable_for_dispatch": True,
                "move_on_allowed": True,
                "search_allowed": True,
                "needs_confirmation": False,
                "reason": "anchored_note",
            }
        if name == "lookup_address":
            return {
                "found": True,
                "geocoded": True,
                "normalized_address": "Donaustraße 44, 12043 Berlin, Germany",
                "lat": 52.4799,
                "lon": 13.4394,
                "source": "google_geocoding",
                "confidence": "high",
                "reason": "google_match",
            }
        return original_dispatch_tool_call(name, args)

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "dispatch_tool_call", fake_dispatch_tool_call)
    monkeypatch.setattr(server, "analyze_session_triage", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("triage should not run in llm_only mode")))

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "triage_mode": "llm_only",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "I am being held hostage close to Delta campus, fourth floor, and they have a gun."}
                ],
                "agent": [],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dispatch_update"]["prompt_context"]["human_monitoring"] is True
    session = server.get_session(session_id)
    tool_names = [tool["name"] for tool in session.get("tool_calls", [])]
    assert "plan_response_services" in tool_names
    assert "simulate_dispatch_services" in tool_names
    assert "create_incident_ticket" in tool_names
    assert session["dispatch_services"]["services"]["police"]["needed"] is True
