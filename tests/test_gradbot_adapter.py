from emergency_dispatcher.gradbot_adapter import build_session_config


def test_session_config_is_caller_led_and_less_eager():
    config = build_session_config()

    assert config.assistant_speaks_first is False
    assert config.flush_duration_s >= 1.2
    assert config.silence_timeout_s >= 6.5
    assert len(config.instructions) < 4000
    assert "What is your emergency?" in config.instructions
    assert "Do not interrupt the caller's opening sentence" in config.instructions
    assert "use `checklist_by_incident` before deciding the next hard-fact question" in config.instructions
    assert "use `resolve_location_note` for landmarks, entrances, floors, rooms, and relative clues" in config.instructions
    assert "normalize_place_name" not in config.instructions


def test_session_config_gets_more_patient_after_interruptions():
    config = build_session_config(interrupt_count=2, interruption_recovery=True)

    assert config.assistant_speaks_first is False
    assert config.flush_duration_s > 1.25
    assert config.silence_timeout_s > 6.5
    assert "Adaptive turn-taking policy:" in config.instructions
    assert "Please repeat that last part." in config.instructions
    assert "Immediate recovery instruction:" in config.instructions


def test_session_config_forces_binary_medical_confirmation_when_ambiguous():
    config = build_session_config()

    assert "Is she breathing right now? Yes or no." in config.instructions
    assert "Is there heavy bleeding? Yes or no." in config.instructions
    assert "do not reconfirm life-status over and over" in config.instructions


def test_session_config_embeds_triage_context_for_llm_guidance():
    config = build_session_config(
        triage_context={
            "version": 2,
            "selected_engine": "heuristic",
            "runtime_provider": "heuristic",
            "raw_utterance": "My partner is bleeding near Delta Campus.",
            "latest_triage_delta": {
                "location": "Delta Campus",
                "issue_type": "VEHICLE_ACCIDENT_WITH_INJURY",
                "priority": "CRITICAL",
                "victim_breathing": "unknown",
                "victim_bleeding": "yes",
                "victim_conscious": "unknown",
                "victim_count": "unknown",
                "caller_safe": "unknown",
                "escalate_to_human": True,
                "escalation_reason": "priority_critical",
                "severity_score": 90,
                "severity_delta": 55,
                "severity_drivers": ["heavy_bleeding"],
                "human_recommended": True,
                "human_required": True,
                "constraint_mode": "holding_pattern_only",
                "address_in_utterance": True,
            },
            "merged_triage_state": {
                "location": "Delta Campus",
                "issue_type": "VEHICLE_ACCIDENT_WITH_INJURY",
                "priority": "CRITICAL",
                "victim_breathing": "unknown",
                "victim_bleeding": "yes",
                "victim_conscious": "unknown",
                "victim_count": "unknown",
                "caller_safe": "unknown",
                "escalate_to_human": True,
                "escalation_reason": "priority_critical",
                "severity_score": 90,
                "severity_delta": 55,
                "severity_drivers": ["heavy_bleeding"],
                "human_recommended": True,
                "human_required": True,
                "constraint_mode": "holding_pattern_only",
                "address_in_utterance": True,
            },
            "missing_or_unknown_fields": ["victim_breathing", "victim_conscious"],
            "rule_overrides": [],
            "handoff_packet": {"status": "ready_for_human_handoff"},
            "dispatchable": True,
            "autonomy_allowed": False,
            "gliner_entities": [{"label": "LOCATION", "text": "Delta Campus", "confidence": 0.98}],
            "stt_rescue": {
                "corrected_transcript": "My partner is bleeding near Delta Campus.",
                "ask_for_repeat": True,
                "location_needs_spelling": True,
            },
        }
    )

    assert "Live triage packet:" in config.instructions
    assert "ask the caller to spell the key word" in config.instructions
    assert "respect constraint_mode exactly" in config.instructions
    assert "never call validate_address or lookup_address unless location_search_allowed is true" in config.instructions
    assert "prefer one relevant deterministic tool call before a follow-up" in config.instructions
    assert "do not ask again for a fact already resolved" in config.instructions
    assert "next_question_field" in config.instructions
    assert "location_search_allowed" in config.instructions
    assert "rescue_text" in config.instructions
