import uuid

from fastapi.testclient import TestClient

from emergency_dispatcher import server
from emergency_dispatcher.server import app
from emergency_dispatcher.settings import get_settings
from emergency_dispatcher.slm_fact_ledger import empty_shared_ledger
from emergency_dispatcher.stt_rescue import RescueCandidate
from emergency_dispatcher.stt_rescue import STTRescueEvent


client = TestClient(app)


def test_session_report_returns_ledger_update(monkeypatch):
    server_settings = get_settings().model_copy(
        update={
            "triage_engine": "slm",
            "triage_api_key": "test-key",
            "live_fact_ledger_model": "fact-ledger-model",
        }
    )
    monkeypatch.setattr(server, "_ensure_live_runtime_ready_http", lambda mode: server_settings)
    async def fake_rescue(**kwargs):
        return None

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "_auto_dispatch_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_shared_ledger_refresh", lambda *args, **kwargs: None)

    ledger = empty_shared_ledger()
    ledger["version"] = 2
    ledger["hard_facts"]["location_candidate"] = "Delta Campus"
    ledger["hard_facts"]["location_kind"] = "place_name"
    ledger["hard_facts"]["issue_cues"] = ["bleeding"]
    ledger["priority"]["missing_fields"] = ["victim_count_confirmed"]
    ledger["priority"]["next_question_field"] = "victim_count_confirmed"
    ledger["priority"]["next_question_goal"] = "confirm how many people are involved"
    monkeypatch.setattr(server, "_refresh_shared_ledger_runtime", lambda *args, **kwargs: ledger)

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
    assert payload["triage_update"] is None
    assert payload["ledger_update"]["prompt_context"]["known"]["location_candidate"] == "Delta Campus"
    assert payload["ledger_update"]["prompt_context"]["missing_fields"] == ["victim_count_confirmed"]


def test_session_report_includes_stt_rescue_event(monkeypatch):
    monkeypatch.setattr(
        server,
        "_ensure_live_runtime_ready_http",
        lambda mode: get_settings().model_copy(
            update={
                "triage_engine": "slm",
                "triage_api_key": "test-key",
                "live_fact_ledger_model": "fact-ledger-model",
            }
        ),
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
    monkeypatch.setattr(server, "_auto_dispatch_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_shared_ledger_refresh", lambda *args, **kwargs: None)
    ledger = empty_shared_ledger()
    ledger["version"] = 1
    ledger["priority"]["missing_fields"] = ["issue_cues"]
    ledger["priority"]["next_question_field"] = "issue_cues"
    ledger["priority"]["next_question_goal"] = "clarify the emergency"
    monkeypatch.setattr(server, "_refresh_shared_ledger_runtime", lambda *args, **kwargs: ledger)

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
    assert payload["ledger_update"]["prompt_context"]["next_question_goal"] == "clarify the emergency"


def test_session_report_slm_location_flow_confirms_runtime_candidate(monkeypatch):
    server_settings = get_settings().model_copy(
        update={
            "triage_engine": "slm",
            "triage_api_key": "test-key",
            "live_fact_ledger_model": "fact-ledger-model",
        }
    )
    monkeypatch.setattr(server, "_ensure_live_runtime_ready_http", lambda mode: server_settings)

    async def fake_rescue(**kwargs):
        return None

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "_auto_dispatch_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_shared_ledger_refresh", lambda *args, **kwargs: None)

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "There is smoke around me."},
                    {"at": "2026-04-25T00:00:05Z", "text": "The nearest exit is Donnerausstraße."},
                ],
                "agent": [
                    {"at": "2026-04-25T00:00:03Z", "text": "Where are you right now?"},
                ],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    prompt_context = payload["ledger_update"]["prompt_context"]
    assert prompt_context["location_followup_kind"] == "confirm_candidate"
    assert prompt_context["location_followup_prompt"].endswith("Is that correct? Yes or no.")
    assert prompt_context["location_search_allowed"] is True
    session = server.get_session(session_id)
    tool_names = [tool["name"] for tool in session.get("tool_calls", [])]
    assert "resolve_location_note" in tool_names
    assert "lookup_address" in tool_names


def test_session_report_slm_location_flow_ignores_bare_strasse_fragment(monkeypatch):
    server_settings = get_settings().model_copy(
        update={
            "triage_engine": "slm",
            "triage_api_key": "test-key",
            "live_fact_ledger_model": "fact-ledger-model",
        }
    )
    monkeypatch.setattr(server, "_ensure_live_runtime_ready_http", lambda mode: server_settings)

    async def fake_rescue(**kwargs):
        return None

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "_auto_dispatch_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_shared_ledger_refresh", lambda *args, **kwargs: None)

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "There is smoke around me."},
                    {"at": "2026-04-25T00:00:05Z", "text": "Strasse."},
                ],
                "agent": [
                    {"at": "2026-04-25T00:00:03Z", "text": "Where are you right now?"},
                ],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    prompt_context = payload["ledger_update"]["prompt_context"]
    assert prompt_context["location_followup_kind"] == "ask_exact_address"
    assert prompt_context["location_followup_prompt"] == "Do you know the exact address? If you do, say it slowly."
    session = server.get_session(session_id)
    tool_names = [tool["name"] for tool in session.get("tool_calls", [])]
    assert "lookup_address" not in tool_names


def test_runtime_fallback_does_not_treat_greeting_as_location():
    session = {
        "client": {
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "Hello, can you help me?"},
                ]
            }
        }
    }

    hard_facts = server._runtime_fallback_hard_facts(session)

    assert hard_facts["location_candidate"] is None
    assert hard_facts["location_kind"] == "none"
    assert hard_facts["address_in_utterance"] is False


def test_runtime_location_parser_rejects_non_location_chatter():
    candidate, note, sub_location = server._infer_location_bundle_from_text("Hello, can you help me?")

    assert candidate is None
    assert note is None
    assert sub_location is None


def test_session_report_slm_location_flow_moves_to_spell_after_rejected_confirmation(monkeypatch):
    server_settings = get_settings().model_copy(
        update={
            "triage_engine": "slm",
            "triage_api_key": "test-key",
            "live_fact_ledger_model": "fact-ledger-model",
        }
    )
    monkeypatch.setattr(server, "_ensure_live_runtime_ready_http", lambda mode: server_settings)

    async def fake_rescue(**kwargs):
        return None

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "_auto_dispatch_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_shared_ledger_refresh", lambda *args, **kwargs: None)

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "The nearest exit is Donnerausstraße."},
                    {"at": "2026-04-25T00:00:07Z", "text": "No."},
                ],
                "agent": [
                    {"at": "2026-04-25T00:00:03Z", "text": "You said Donnerausstraße. Is that correct? Yes or no."},
                ],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    prompt_context = payload["ledger_update"]["prompt_context"]
    assert prompt_context["location_followup_kind"] == "ask_spell"
    assert "spell the street or place name slowly" in prompt_context["location_followup_prompt"]


def test_session_report_slm_prefers_mapped_candidate_for_confirmation(monkeypatch):
    server_settings = get_settings().model_copy(
        update={
            "triage_engine": "slm",
            "triage_api_key": "test-key",
            "live_fact_ledger_model": "fact-ledger-model",
        }
    )
    monkeypatch.setattr(server, "_ensure_live_runtime_ready_http", lambda mode: server_settings)

    async def fake_rescue(**kwargs):
        return None

    original_dispatch_tool_call = server.dispatch_tool_call

    def fake_dispatch_tool_call(name, args):
        if name == "lookup_address" and (args or {}).get("address_text") == "Delta Campus":
            return {
                "found": True,
                "geocoded": True,
                "normalized_address": "Donaustraße 44, 12043 Berlin, Germany",
                "display_name": "Donaustraße 44, 12043 Berlin, Germany",
                "lat": 52.4799,
                "lon": 13.4394,
                "source": "google_geocoding",
                "confidence": "high",
                "reason": "google_match",
                "candidate_only": True,
                "requires_confirmation": True,
                "location_query_reason": "place_name",
            }
        return original_dispatch_tool_call(name, args)

    monkeypatch.setattr(server, "maybe_run_stt_rescue", fake_rescue)
    monkeypatch.setattr(server, "dispatch_tool_call", fake_dispatch_tool_call)
    monkeypatch.setattr(server, "_auto_dispatch_services", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_shared_ledger_refresh", lambda *args, **kwargs: None)

    session_id = f"test-{uuid.uuid4()}"
    response = client.post(
        "/api/session-report",
        json={
            "session_id": session_id,
            "status": "live",
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "There was an accident at Delta Campus."},
                ],
                "agent": [
                    {"at": "2026-04-25T00:00:03Z", "text": "Where are you right now?"},
                ],
            },
            "events": [],
            "metrics": {},
            "page": {"href": "http://localhost/demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    prompt_context = payload["ledger_update"]["prompt_context"]
    assert prompt_context["known"]["location_candidate"] == "Donaustraße 44, 12043 Berlin, Germany"
    assert prompt_context["location_followup_kind"] == "confirm_candidate"
    assert prompt_context["location_followup_prompt"] == "I found Donaustraße 44, 12043 Berlin, Germany. Is that correct? Yes or no."
    assert prompt_context["must_say_next"] == "I found Donaustraße 44, 12043 Berlin, Germany. Is that correct? Yes or no."


def test_merge_shared_hard_facts_preserves_meaningful_location_and_cues():
    existing = empty_shared_ledger()["hard_facts"]
    existing.update(
        {
            "location_candidate": "Friedrichstrasse",
            "location_kind": "road_or_junction",
            "address_in_utterance": True,
            "issue_cues": ["collision", "smoke"],
            "bleeding_status": "no",
        }
    )
    incoming = empty_shared_ledger()["hard_facts"]
    incoming.update(
        {
            "location_candidate": None,
            "location_kind": "none",
            "address_in_utterance": False,
            "issue_cues": [],
            "bleeding_status": "unknown",
        }
    )

    merged = server._merge_shared_hard_facts(existing, incoming)

    assert merged["location_candidate"] == "Friedrichstrasse"
    assert merged["location_kind"] == "road_or_junction"
    assert merged["issue_cues"] == ["collision", "smoke"]
    assert merged["bleeding_status"] == "no"


def test_runtime_fallback_prefers_clean_reconstruction_location():
    session = {
        "server": {
            "enhancement": {
                "clean_reconstruction": "I am near Templehofer Feld and I had an accident.",
                "raw_reconstruction": "I am near Temple Hoferfeld and I had an accident.",
            }
        },
        "client": {
            "transcripts": {
                "user": [
                    {"text": "I am near Temple Hoferfeld."},
                    {"text": "I had an accident."},
                ]
            }
        },
        "tool_calls": [],
    }

    hard_facts = server._runtime_fallback_hard_facts(session)

    assert hard_facts["location_candidate"] == "Templehofer Feld"
    assert "collision" in hard_facts["issue_cues"]


def test_derive_dispatch_inputs_does_not_dispatch_unconfirmed_location():
    ledger = empty_shared_ledger()
    ledger["hard_facts"]["location_candidate"] = "Friedrichstrasse"
    ledger["hard_facts"]["location_kind"] = "road_or_junction"
    ledger["location_gate"]["candidate_text"] = "Friedrichstrasse"
    ledger["location_gate"]["candidate_kind"] = "road_or_junction"
    ledger["location_gate"]["search_allowed"] = False
    ledger["location_gate"]["confirmed"] = False

    session = {
        "shared_ledger": ledger,
        "client": {
            "transcripts": {
                "user": [
                    {"at": "2026-04-25T00:00:00Z", "text": "I had an accident and I am close to Friedrichstrasse, Berlin."}
                ]
            }
        },
        "tool_calls": [
            {
                "name": "resolve_location_note",
                "args": {
                    "location_candidate": "Friedrichstrasse",
                    "location_note": "close to Friedrichstrasse, Berlin",
                },
                "result": {
                    "anchor_location": "Friedrichstrasse",
                    "normalized_note": "close to Friedrichstrasse, Berlin",
                },
            }
        ],
    }

    dispatch_inputs = server._derive_dispatch_inputs(session)

    assert dispatch_inputs["location_text"] == "Friedrichstrasse"
    assert dispatch_inputs["dispatch_location_text"] is None
    assert dispatch_inputs["location_confirmed"] is False


def test_derive_dispatch_inputs_ignores_ticket_address_when_slm_location_unconfirmed():
    ledger = empty_shared_ledger()
    ledger["location_gate"]["confirmed"] = False
    ledger["location_gate"]["candidate_only"] = True
    ledger["location_gate"]["candidate_text"] = "Donaustraße 44, 12043 Berlin, Germany"
    session = {
        "shared_ledger": ledger,
        "server": {"live_dispatch_mode": "slm"},
        "client": {"transcripts": {"user": [{"at": "2026-04-25T00:00:00Z", "text": "I am at Delta Campus."}]}},
        "tool_calls": [
            {
                "name": "create_incident_ticket",
                "args": {"address": "Delta Campus, front entrance"},
                "result": {"address": "Delta Campus, front entrance"},
            },
            {
                "name": "lookup_address",
                "args": {"address_text": "Delta Campus"},
                "result": {
                    "normalized_address": "Donaustraße 44, 12043 Berlin, Germany",
                    "candidate_only": True,
                    "lat": 52.4799,
                    "lon": 13.4394,
                },
            },
        ],
    }

    dispatch_inputs = server._derive_dispatch_inputs(session)

    assert dispatch_inputs["location_text"] == "Donaustraße 44, 12043 Berlin, Germany"
    assert dispatch_inputs["dispatch_location_text"] is None
    assert dispatch_inputs["location_confirmed"] is False


def test_ledger_location_gate_does_not_confirm_road_candidate_from_tools_alone():
    ledger = empty_shared_ledger()
    ledger["hard_facts"]["location_candidate"] = "Oxford Strassen, Berlin"
    ledger["hard_facts"]["location_kind"] = "road_or_junction"
    session = {
        "shared_ledger": ledger,
        "tool_calls": [
            {
                "name": "lookup_address",
                "args": {"address_text": "Oxford Strassen, Berlin", "allow_best_effort": True},
                "result": {
                    "normalized_address": "Fasanenstraße 6, 10623 Berlin, Germany",
                    "lat": 52.5069,
                    "lon": 13.3277,
                    "candidate_only": False,
                    "location_query_reason": "road_or_junction",
                },
            }
        ],
    }

    gate = server._ledger_location_gate(ledger, session, location_followup={})

    assert gate["confirmed"] is False
    assert gate["candidate_only"] is True
    assert gate["search_reason"] != "confirmed_by_tools"


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
