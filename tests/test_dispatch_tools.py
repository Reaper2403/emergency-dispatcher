import json

import pytest

from emergency_dispatcher import dispatch_tools
from emergency_dispatcher.dispatch_tools import assign_dispatch_priority
from emergency_dispatcher.dispatch_tools import build_handoff_brief
from emergency_dispatcher.dispatch_tools import build_gradbot_tool_defs
from emergency_dispatcher.dispatch_tools import checklist_by_incident
from emergency_dispatcher.dispatch_tools import infer_issue_type
from emergency_dispatcher.dispatch_tools import lookup_address
from emergency_dispatcher.dispatch_tools import lookup_response_bases
from emergency_dispatcher.dispatch_tools import nearby_context
from emergency_dispatcher.dispatch_tools import plan_response_services
from emergency_dispatcher.dispatch_tools import resolve_location_note
from emergency_dispatcher.dispatch_tools import run_dispatch_workflow
from emergency_dispatcher.dispatch_tools import simulate_dispatch_services
from emergency_dispatcher.dispatch_tools import validate_address


@pytest.fixture(autouse=True)
def stub_geocoders(monkeypatch):
    monkeypatch.setattr(dispatch_tools, "_google_geocode_candidates", lambda _query: [])

    def fake_candidates(query):
        if "Müllerstraße" in query:
            return [
                {
                    "display_name": "128 Müllerstraße, Wedding, Berlin, Germany",
                    "lat": "52.551",
                    "lon": "13.362",
                    "type": "road",
                    "class": "highway",
                    "importance": 0.72,
                    "address": {
                        "suburb": "Wedding",
                        "city": "Berlin",
                        "state": "Berlin",
                        "country": "Germany",
                    },
                }
            ]
        if "Main Street" in query:
            return [
                {
                    "display_name": "128 Main Street, Berlin, Germany",
                    "lat": "52.520",
                    "lon": "13.405",
                    "type": "road",
                    "class": "highway",
                    "importance": 0.62,
                    "address": {
                        "city": "Berlin",
                        "state": "Berlin",
                        "country": "Germany",
                    },
                }
            ]
        return []

    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", fake_candidates)
    monkeypatch.setattr(
        dispatch_tools,
        "_overpass_context",
        lambda _lat, _lon: {
            "major_roads": [],
            "landmarks": [],
            "named_areas": [],
            "water_features": [],
        },
    )


def test_infer_issue_type_medical():
    assert infer_issue_type("The patient collapsed and is not breathing.") == "MEDICAL"


def test_dispatch_workflow_marks_fire_as_critical():
    result = run_dispatch_workflow(
        "Please hurry, I am at 128 Main Street, Berlin and there is smoke and an explosion risk."
    )
    assert result.issue_type == "FIRE"
    assert result.priority["priority"] in {"HIGH", "CRITICAL"}
    assert result.ticket["status"] == "ready_for_dispatch"


def test_dispatch_workflow_extracts_street_first_address():
    result = run_dispatch_workflow(
        "Please hurry, I am on Müllerstraße near number 128, Berlin and a car is on fire."
    )
    assert result.address_lookup["found"] is True
    assert result.ticket["address"] == "128 Müllerstraße, Wedding, Berlin, Germany"


def test_priority_tool_normalizes_free_form_labels():
    result = assign_dispatch_priority(
        issue_type="traffic accident",
        safety_risk="unknown, potentially high until confirmed",
        caller_state="caller reporting an accident, details unclear",
    )
    assert result["normalized_issue_type"] == "TRAFFIC"
    assert result["normalized_safety_risk"] == "ELEVATED"
    assert result["normalized_caller_state"] == "UNCERTAIN"
    assert result["priority"] in {"MEDIUM", "HIGH", "CRITICAL"}


def test_validate_address_uses_geocoding_when_available(monkeypatch):
    def fake_candidates(_query):
        return [
            {
                "display_name": "Müllerstraße 128, Wedding, Berlin, Germany",
                "lat": "52.551",
                "lon": "13.362",
                "type": "road",
                "class": "highway",
                "importance": 0.72,
                "address": {
                    "suburb": "Wedding",
                    "city": "Berlin",
                    "state": "Berlin",
                    "country": "Germany",
                },
            }
        ]

    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", fake_candidates)

    result = validate_address("128 Müllerstraße, Berlin")

    assert result["valid"] is True
    assert result["geocoded"] is True
    assert result["source"] == "nominatim"
    assert result["lat"] == 52.551
    assert result["lon"] == 13.362
    assert result["normalized_address"] == "Müllerstraße 128, Wedding, Berlin, Germany"


def test_validate_address_prefers_google_when_available(monkeypatch):
    monkeypatch.setattr(
        dispatch_tools,
        "_google_geocode_candidates",
        lambda _query: [
            {
                "formatted_address": "Donaustraße 44, 12043 Berlin, Germany",
                "place_id": "test-place-id",
                "types": ["street_address"],
                "geometry": {
                    "location": {
                        "lat": 52.4799051,
                        "lng": 13.4394434,
                    },
                    "location_type": "ROOFTOP",
                },
                "address_components": [
                    {"long_name": "Donaustraße 44", "types": ["route"]},
                    {"long_name": "Berlin", "types": ["locality"]},
                    {"long_name": "Berlin", "types": ["administrative_area_level_1"]},
                    {"long_name": "Germany", "types": ["country"]},
                ],
            }
        ],
    )
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", lambda _query: [])

    result = validate_address("Delta Campus Berlin")

    assert result["valid"] is True
    assert result["geocoded"] is True
    assert result["source"] == "google_geocoding"
    assert result["confidence"] == "high"
    assert result["normalized_address"] == "Donaustraße 44, 12043 Berlin, Germany"
    assert result["lat"] == 52.4799051
    assert result["lon"] == 13.4394434


def test_lookup_address_google_result_is_json_serializable(monkeypatch):
    monkeypatch.setattr(
        dispatch_tools,
        "_google_geocode_candidates",
        lambda _query: [
            {
                "formatted_address": "Donaustraße 44, 12043 Berlin, Germany",
                "place_id": "test-place-id",
                "types": ["street_address"],
                "geometry": {
                    "location": {
                        "lat": 52.4799051,
                        "lng": 13.4394434,
                    },
                    "location_type": "ROOFTOP",
                },
                "address_components": [
                    {"long_name": "Donaustraße 44", "types": ["route"]},
                    {"long_name": "Berlin", "types": ["locality"]},
                    {"long_name": "Berlin", "types": ["administrative_area_level_1"]},
                    {"long_name": "Germany", "types": ["country"]},
                ],
            }
        ],
    )
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", lambda _query: [])

    result = lookup_address("Delta Campus Berlin")

    json.dumps(result)
    assert result["candidates"][0]["display_name"] == "Donaustraße 44, 12043 Berlin, Germany"
    assert result["candidates"][0] is not result


def test_validate_address_rejects_generic_google_city_match(monkeypatch):
    monkeypatch.setattr(
        dispatch_tools,
        "_google_geocode_candidates",
        lambda _query: [
            {
                "formatted_address": "Berlin, Germany",
                "place_id": "generic-berlin",
                "types": ["locality", "political"],
                "geometry": {
                    "location": {
                        "lat": 52.5200066,
                        "lng": 13.404954,
                    },
                    "location_type": "APPROXIMATE",
                },
                "address_components": [
                    {"long_name": "Berlin", "types": ["locality"]},
                    {"long_name": "Berlin", "types": ["administrative_area_level_1"]},
                    {"long_name": "Germany", "types": ["country"]},
                ],
            }
        ],
    )
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", lambda _query: [])

    result = validate_address("Reeperbahn 1")

    assert result["geocoded"] is False
    assert result["source"] == "text_fallback"


def test_lookup_address_falls_back_when_geocoder_returns_no_match(monkeypatch):
    monkeypatch.setattr(dispatch_tools, "_google_geocode_candidates", lambda _query: [])
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", lambda _query: [])

    result = lookup_address("12 Quartz Road, Berlin")

    assert result["found"] is False
    assert result["geocoded"] is False
    assert result["source"] == "text_fallback"
    assert result["normalized_address"] == "12 Quartz Road, Berlin"
    assert result["reason"] in {"nominatim_no_match", "google_no_match_nominatim_no_match"}


def test_validate_address_rejects_vague_location_phrase_without_geocoding(monkeypatch):
    google_called = False
    nominatim_called = False

    def fake_google(_query):
        nonlocal google_called
        google_called = True
        return []

    def fake_nominatim(_query):
        nonlocal nominatim_called
        nominatim_called = True
        return []

    monkeypatch.setattr(dispatch_tools, "_google_geocode_candidates", fake_google)
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", fake_nominatim)

    result = validate_address("middle of the street")

    assert result["valid"] is False
    assert result["geocoded"] is False
    assert result["source"] == "guardrail"
    assert result["reason"] == "location_not_specific_enough"
    assert google_called is False
    assert nominatim_called is False


def test_lookup_address_rejects_vague_location_phrase_without_geocoding(monkeypatch):
    google_called = False
    nominatim_called = False

    def fake_google(_query):
        nonlocal google_called
        google_called = True
        return []

    def fake_nominatim(_query):
        nonlocal nominatim_called
        nominatim_called = True
        return []

    monkeypatch.setattr(dispatch_tools, "_google_geocode_candidates", fake_google)
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", fake_nominatim)

    result = lookup_address("inside the building")

    assert result["found"] is False
    assert result["geocoded"] is False
    assert result["source"] == "guardrail"
    assert result["reason"] == "location_not_specific_enough"
    assert result["location_context"] is None
    assert google_called is False
    assert nominatim_called is False


def test_validate_address_allows_searchable_street_suffix_phrase(monkeypatch):
    google_called = False
    nominatim_called = False

    def fake_google(_query):
        nonlocal google_called
        google_called = True
        return []

    def fake_nominatim(_query):
        nonlocal nominatim_called
        nominatim_called = True
        return []

    monkeypatch.setattr(dispatch_tools, "_google_geocode_candidates", fake_google)
    monkeypatch.setattr(dispatch_tools, "_nominatim_candidates", fake_nominatim)

    result = validate_address("Mullerstrasse near number 128 in Berlin")

    assert result["source"] == "text_fallback"
    assert result["reason"] in {"nominatim_no_match", "google_no_match_nominatim_no_match"}
    assert google_called is True or nominatim_called is True


def test_nominatim_candidates_biases_queries_into_berlin(monkeypatch):
    params = dispatch_tools._nominatim_query_params("Müllerstraße 128")

    assert params["q"] == "Müllerstraße 128, Berlin"
    assert params["bounded"] == 1
    assert params["viewbox"] == dispatch_tools.BERLIN_VIEWBOX


def test_resolve_location_note_preserves_landmark_without_fake_pin():
    result = resolve_location_note("behind the red brick church", sub_location="west entrance")

    assert result["note_type"] == "landmark_relative"
    assert result["location_status"] == "best_effort_note"
    assert result["usable_for_dispatch"] is True
    assert result["search_allowed"] is False
    assert result["sub_location"] == "west entrance"


def test_resolve_location_note_promotes_new_street_anchor_from_note():
    result = resolve_location_note(
        "Near Müllerstraße, outside the subway station, toward the sea exit.",
        location_candidate="Alexander Platz",
        sub_location="outside the subway station, toward the sea exit",
    )

    assert result["anchor_location"] == "Müllerstraße"
    assert result["search_allowed"] is True
    assert result["location_status"] == "usable_place"


def test_nearby_context_returns_summary_for_geocoded_address():
    result = nearby_context(address_text="128 Müllerstraße, Berlin")

    assert result["resolved"] is True
    assert result["normalized_address"] == "128 Müllerstraße, Wedding, Berlin, Germany"
    assert result["summary"]
    assert result["reason"] in {"nominatim+overpass", "nominatim_only"}


def test_checklist_by_incident_prioritizes_location_anchor_after_issue():
    result = checklist_by_incident(
        {
            "issue_cues": ["fire"],
            "location_note": "behind the supermarket",
            "sub_location": "rear stairwell",
            "victim_count": "unknown",
        }
    )

    assert result["location_status"] == "best_effort_note"
    assert result["missing_fields"][0] == "location_anchor"
    assert result["next_question_field"] == "location_candidate"
    assert result["location_search_allowed"] is False


def test_build_handoff_brief_summarizes_best_effort_dispatch_state():
    result = build_handoff_brief(
        caller_summary="There is smoke behind the supermarket by the rear stairwell.",
        args={
            "issue_cues": ["smoke", "fire"],
            "location_note": "behind the supermarket",
            "sub_location": "rear stairwell",
            "victim_count": 2,
        },
    )

    assert result["status"] == "dispatchable_with_note"
    assert "smoke" in result["one_line"]
    assert "Best effort location note" in result["dispatcher_note"]
    assert "location anchor" in " ".join(result["unknowns"])


def test_live_gradbot_tool_set_keeps_fact_tools_and_retires_weak_ones():
    tool_names = [name for name, _description, _schema in build_gradbot_tool_defs()]

    assert tool_names == [
        "resolve_location_note",
        "checklist_by_incident",
        "validate_address",
        "lookup_address",
        "nearby_context",
        "build_handoff_brief",
        "create_incident_ticket",
    ]


def test_plan_response_services_flags_hostage_call_for_police_and_ambulance():
    result = plan_response_services(
        transcript="I am being held hostage, they have a gun, and my daughter is bleeding.",
        issue_type="POLICE",
    )

    assert result["human_monitoring"] is True
    assert result["monitor_name"] == "Alex"
    assert result["priority"] == "CRITICAL"
    assert result["services"]["police"]["needed"] is True
    assert result["services"]["ambulance"]["needed"] is True


def test_simulate_dispatch_services_transitions_to_dispatched():
    plan = plan_response_services(
        transcript="There is smoke coming from the apartment and someone is trapped inside.",
        issue_type="FIRE",
    )
    first = simulate_dispatch_services(
        session_id="demo-session",
        plan=plan,
        location_text="Müllerstraße 128, Berlin",
        location_confirmed=True,
        now_iso="2026-04-26T01:00:00+00:00",
    )
    later = simulate_dispatch_services(
        session_id="demo-session",
        plan=plan,
        location_text="Müllerstraße 128, Berlin",
        location_confirmed=True,
        prior_state=first,
        now_iso="2026-04-26T01:00:05+00:00",
    )

    assert later["dispatchable"] is True
    assert later["services"]["fire"]["status"] == "dispatched"
    assert later["services"]["ambulance"]["status"] == "dispatched"


def test_lookup_response_bases_returns_grounded_service_locations(monkeypatch):
    monkeypatch.setattr(dispatch_tools, "_google_response_bases", lambda _lat, _lon: {})
    monkeypatch.setattr(
        dispatch_tools,
        "_overpass_response_bases",
        lambda _lat, _lon: {
            "police": {
                "display_name": "Abschnitt 52",
                "address": "Musterstraße 10, 10115 Berlin",
                "lat": 52.53,
                "lon": 13.40,
                "distance_km": 0.9,
                "eta_min": 5,
                "eta_text": "5 mins",
                "source_type": "police",
            }
        },
    )

    result = lookup_response_bases(lat=52.52, lon=13.405, location_text="Berlin Mitte")

    assert result["resolved"] is True
    assert result["services"]["police"]["display_name"] == "Abschnitt 52"
    assert result["services"]["police"]["eta_text"] == "5 mins"


def test_simulate_dispatch_services_uses_response_base_details():
    plan = plan_response_services(
        transcript="There is smoke coming from the apartment and someone is trapped inside.",
        issue_type="FIRE",
    )
    result = simulate_dispatch_services(
        session_id="demo-session",
        plan=plan,
        location_text="Müllerstraße 128, Berlin",
        location_confirmed=True,
        response_bases={
            "fire": {
                "display_name": "Feuerwache Wedding",
                "address": "Müllerstraße 12, Berlin",
                "distance_km": 1.4,
                "eta_min": 6,
                "eta_text": "6 mins",
                "source_type": "fire_station",
            }
        },
        now_iso="2026-04-26T01:00:05+00:00",
    )

    assert result["services"]["fire"]["base_name"] == "Feuerwache Wedding"
    assert result["services"]["fire"]["eta_text"] == "6 mins"


def test_simulate_dispatch_services_carries_announcement_briefly_until_next_prompt():
    plan = plan_response_services(
        transcript="I am trapped in a crash and there is smoke.",
        issue_type="FIRE",
    )
    first = simulate_dispatch_services(
        session_id="demo-session",
        plan=plan,
        location_text=None,
        location_confirmed=False,
        now_iso="2026-04-26T01:00:00+00:00",
    )
    assert first["announcement_line"]

    carried = simulate_dispatch_services(
        session_id="demo-session",
        plan=plan,
        location_text=None,
        location_confirmed=False,
        prior_state=first,
        now_iso="2026-04-26T01:00:02+00:00",
    )
    assert carried["announcement_line"] == first["announcement_line"]

    expired = simulate_dispatch_services(
        session_id="demo-session",
        plan=plan,
        location_text=None,
        location_confirmed=False,
        prior_state=first,
        now_iso="2026-04-26T01:00:12+00:00",
    )
    assert expired["announcement_line"] is None
