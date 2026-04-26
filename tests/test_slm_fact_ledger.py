from emergency_dispatcher.slm_fact_ledger import FactLedger
from emergency_dispatcher.slm_fact_ledger import build_fact_delta
from emergency_dispatcher.slm_fact_ledger import build_fact_priority_packet
from emergency_dispatcher.slm_fact_ledger import build_pioneer_fact_ledger_record
from emergency_dispatcher.slm_fact_ledger import has_dispatchable_location_cue


def test_has_dispatchable_location_cue_rejects_generic_home_and_accepts_address():
    assert has_dispatchable_location_cue("I am at home in Berlin.") is False
    assert has_dispatchable_location_cue("There is smoke near Mullerstrasse 128 in Berlin.") is True


def test_fact_delta_and_priority_packet_focus_on_missing_hard_facts():
    prior = FactLedger(
        location_candidate="Delta Campus building",
        location_kind="place_name",
        inside_building="yes",
        issue_cues=["trapped"],
        trapped_status="yes",
    )
    merged = FactLedger(
        location_candidate="Delta Campus building",
        location_kind="place_name",
        inside_building="yes",
        issue_cues=["trapped", "child_present"],
        trapped_status="yes",
        child_present="yes",
    )

    delta = build_fact_delta(prior, merged)
    packet = build_fact_priority_packet(prior, merged)

    assert delta["child_present"] == "yes"
    assert "child_present" in delta["issue_cues"]
    assert packet["priority_flags"]["next_question_goal"] == "how_many_people"
    assert packet["priority_flags"]["location_search_allowed"] is False
    assert packet["priority_flags"]["best_effort_location_note"] is None


def test_priority_packet_keeps_best_effort_location_note_without_enabling_search():
    prior = FactLedger()
    merged = FactLedger(
        location_kind="none",
        location_note="behind the red brick church",
        address_in_utterance=False,
    )

    packet = build_fact_priority_packet(prior, merged)

    assert packet["priority_flags"]["location_search_allowed"] is False
    assert packet["priority_flags"]["best_effort_location_note"] == "behind the red brick church"


def test_pioneer_record_contains_user_input_and_merged_facts():
    record = build_pioneer_fact_ledger_record(
        {
            "caller_turn": "With my daughter.",
            "prior_facts": FactLedger().model_dump(),
            "merged_facts": FactLedger(
                issue_cues=["child_present"],
                child_present="yes",
            ).model_dump(),
        }
    )

    assert record["messages"][1]["role"] == "user"
    assert "caller_turn" in record["messages"][1]["content"]
    assert record["messages"][2]["role"] == "assistant"
    assert "merged_facts" in record["messages"][2]["content"]
