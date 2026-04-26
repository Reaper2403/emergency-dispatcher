from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


FACT_LEDGER_SCHEMA_VERSION = "2026-04-26.v1"
FACT_YES_NO_UNKNOWN = ("yes", "no", "unknown")
FACT_LOCATION_KINDS = (
    "exact_address",
    "road_or_junction",
    "place_name",
    "sub_location_only",
    "vague",
    "none",
)
FACT_ISSUE_CUES = (
    "vehicle",
    "collision",
    "injury",
    "bleeding",
    "breathing_problem",
    "unconscious",
    "smoke",
    "fire",
    "trapped",
    "weapon",
    "explosion",
    "gas_smell",
    "child_present",
)
FACT_PRIORITY_FIELDS = (
    "issue_cues",
    "location_candidate",
    "victim_count",
    "breathing_status",
    "bleeding_status",
    "consciousness_status",
    "trapped_status",
)

FACT_LEDGER_SYSTEM_PROMPT = """You update a strict evidence-only fact ledger for a live emergency dispatch assistant.
Return JSON only.
Do not include markdown.

Use exactly this top-level shape:
{
  "merged_facts": {
    "location_candidate": "string or null",
    "location_kind": "one of exact_address, road_or_junction, place_name, sub_location_only, vague, none",
    "address_in_utterance": true,
    "location_note": "string or null",
    "sub_location": "string or null",
    "inside_building": "yes|no|unknown",
    "issue_cues": ["zero or more from vehicle, collision, injury, bleeding, breathing_problem, unconscious, smoke, fire, trapped, weapon, explosion, gas_smell, child_present"],
    "victim_count": "integer or unknown",
    "child_present": "yes|no|unknown",
    "bleeding_status": "yes|no|unknown",
    "breathing_status": "yes|no|unknown",
    "consciousness_status": "yes|no|unknown",
    "trapped_status": "yes|no|unknown"
  }
}

Rules:
- Use only hard facts directly stated in caller_turn or already present in prior_facts.
- Carry forward prior_facts unless caller_turn explicitly changes them.
- Do not infer caller safety, severity, threat level, dispatch priority, or escalation.
- Do not invent a location.
- address_in_utterance may be true only if caller_turn itself contains a dispatch-usable location clue.
- location_candidate may stay populated from prior_facts even when address_in_utterance is false.
- location_note may capture a short literal landmark or relative-location clue from caller_turn even when location_candidate is null.
- Generic phrases like "at home", "inside the building", "somewhere in Berlin", and "in the middle of the street" are not dispatch-usable locations.
- location_kind=sub_location_only is for floor, unit, stairwell, entrance, room, or similar sub-location without a building/address clue in this turn.
- issue_cues must be explicit, not inferred.
- If caller_turn is just a confirmation like "yes" or "that's correct", keep facts unless the turn explicitly changes them.
- If caller_turn is a negation like "no bleeding" or "not trapped", update only the directly negated field.
"""

_GENERIC_LOCATION_PATTERN = re.compile(
    r"\b("
    r"at home|home|my house|my apartment|inside the building|inside the house|inside my house|inside my apartment|"
    r"somewhere in berlin|berlin|middle of the street|in the middle of the street|on the street|in the street|"
    r"inside|upstairs|downstairs|third floor|second floor|first floor"
    r")\b",
    flags=re.IGNORECASE,
)
_ADDRESS_PATTERN = re.compile(
    r"\d{1,4}\s+[A-Za-zÀ-ÿ0-9.'-]+(?:\s+[A-Za-zÀ-ÿ0-9.'-]+){0,3}\s+"
    r"(?:street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?|"
    r"strasse|straße|platz|allee|way)\b",
    flags=re.IGNORECASE,
)
_ADDRESS_PATTERN_STREET_FIRST = re.compile(
    r"[A-Za-zÀ-ÿ0-9.'-]+(?:\s+[A-Za-zÀ-ÿ0-9.'-]+){0,3}\s+\d{1,4}\b",
    flags=re.IGNORECASE,
)
_ROAD_OR_JUNCTION_PATTERN = re.compile(
    r"\b(?:A|B|U|S)\s?-?\d{1,4}\b|\b(?:junction|intersection|corner|exit|bridge|tunnel|station|bahnhof)\b",
    flags=re.IGNORECASE,
)
_PLACE_NAME_PATTERN = re.compile(
    r"\b(?:"
    r"delta campus|zoo station|ostkreuz|alexanderplatz|berlin hauptbahnhof|"
    r"hermannplatz|tempelhofer feld|charite campus mitte|mall of berlin|"
    r"neukoelln arcaden|gesundbrunnen station|suedkreuz station|"
    r"(?:[A-Za-zÀ-ÿ0-9.'-]+\s+){1,3}(?:campus|station|bahnhof|hospital|clinic|park|mall|arcaden|center|zentrum|university|schule|school)"
    r")\b",
    flags=re.IGNORECASE,
)
_SUB_LOCATION_PATTERN = re.compile(
    r"\b(?:floor|unit|apartment|flat|room|stairwell|entrance|wing|level)\b",
    flags=re.IGNORECASE,
)


class FactLedger(BaseModel):
    location_candidate: str | None = None
    location_kind: str = "none"
    address_in_utterance: bool = False
    location_note: str | None = None
    sub_location: str | None = None
    inside_building: str = "unknown"
    issue_cues: list[str] = []
    victim_count: int | str = "unknown"
    child_present: str = "unknown"
    bleeding_status: str = "unknown"
    breathing_status: str = "unknown"
    consciousness_status: str = "unknown"
    trapped_status: str = "unknown"

    @field_validator("location_kind")
    @classmethod
    def _validate_location_kind(cls, value: str) -> str:
        if value not in FACT_LOCATION_KINDS:
            raise ValueError(f"Unsupported location_kind: {value}")
        return value

    @field_validator(
        "inside_building",
        "child_present",
        "bleeding_status",
        "breathing_status",
        "consciousness_status",
        "trapped_status",
    )
    @classmethod
    def _validate_yes_no_unknown(cls, value: str) -> str:
        if value not in FACT_YES_NO_UNKNOWN:
            raise ValueError(f"Unsupported yes/no/unknown value: {value}")
        return value

    @field_validator("victim_count", mode="before")
    @classmethod
    def _coerce_victim_count(cls, value: Any) -> int | str:
        if value in (None, "", "unknown"):
            return "unknown"
        if isinstance(value, bool):
            raise ValueError("victim_count cannot be boolean")
        return max(int(value), 0)

    @field_validator("issue_cues")
    @classmethod
    def _validate_issue_cues(cls, value: list[str]) -> list[str]:
        cleaned = [str(item) for item in value or []]
        unknown = [item for item in cleaned if item not in FACT_ISSUE_CUES]
        if unknown:
            raise ValueError(f"Unsupported issue_cues: {', '.join(unknown)}")
        return list(dict.fromkeys(cleaned))

    @field_validator("location_candidate")
    @classmethod
    def _clean_location_candidate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        return cleaned or None

    @field_validator("sub_location")
    @classmethod
    def _clean_sub_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        return cleaned or None

    @field_validator("location_note")
    @classmethod
    def _clean_location_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        return cleaned or None

    def model_post_init(self, __context: Any) -> None:
        if self.location_kind == "none":
            self.location_candidate = None
        if self.location_kind == "vague":
            self.location_candidate = None
            self.address_in_utterance = False
        if self.location_kind == "sub_location_only" and not self.sub_location:
            raise ValueError("sub_location_only requires sub_location")
        if self.location_kind in {"none", "vague"} and self.address_in_utterance:
            raise ValueError("address_in_utterance cannot be true for none/vague location kinds")


class FactLedgerTrainingExample(BaseModel):
    caller_turn: str = Field(min_length=1, max_length=280)
    prior_facts: FactLedger
    merged_facts: FactLedger


def has_dispatchable_location_cue(text: str) -> bool:
    if not text:
        return False
    has_specific = bool(
        _ADDRESS_PATTERN.search(text)
        or _ADDRESS_PATTERN_STREET_FIRST.search(text)
        or _ROAD_OR_JUNCTION_PATTERN.search(text)
        or _PLACE_NAME_PATTERN.search(text)
    )
    if has_specific:
        return True
    if _GENERIC_LOCATION_PATTERN.search(text):
        return False
    return False


def classify_location_kind(text: str) -> str:
    if not text:
        return "none"
    if _ADDRESS_PATTERN.search(text):
        return "exact_address"
    if _ADDRESS_PATTERN_STREET_FIRST.search(text):
        return "exact_address"
    if _ROAD_OR_JUNCTION_PATTERN.search(text):
        return "road_or_junction"
    if _PLACE_NAME_PATTERN.search(text):
        return "place_name"
    if _SUB_LOCATION_PATTERN.search(text):
        return "sub_location_only"
    if _GENERIC_LOCATION_PATTERN.search(text):
        return "vague"
    return "none"


def build_fact_delta(prior_facts: FactLedger, merged_facts: FactLedger) -> dict[str, Any]:
    prior = prior_facts.model_dump()
    merged = merged_facts.model_dump()
    delta: dict[str, Any] = {}
    for key, value in merged.items():
        if value != prior.get(key):
            delta[key] = value
    return delta


def build_fact_priority_packet(prior_facts: FactLedger, merged_facts: FactLedger) -> dict[str, Any]:
    delta = build_fact_delta(prior_facts, merged_facts)
    missing_fields: list[str] = []
    if not merged_facts.issue_cues:
        missing_fields.append("what_is_the_emergency")
    if merged_facts.location_candidate is None or merged_facts.location_kind in {"none", "vague"}:
        missing_fields.append("where_are_you")
    if merged_facts.victim_count == "unknown":
        missing_fields.append("how_many_people")
    if merged_facts.breathing_status == "unknown":
        missing_fields.append("breathing_status")
    if merged_facts.bleeding_status == "unknown":
        missing_fields.append("bleeding_status")
    if merged_facts.consciousness_status == "unknown":
        missing_fields.append("consciousness_status")
    if merged_facts.trapped_status == "unknown":
        missing_fields.append("trapped_status")
    return {
        "facts_delta": delta,
        "priority_flags": {
            "missing_fields": missing_fields,
            "next_question_goal": missing_fields[0] if missing_fields else None,
            "location_search_allowed": bool(
                merged_facts.address_in_utterance
                and merged_facts.location_kind in {"exact_address", "road_or_junction", "place_name"}
                and merged_facts.location_candidate
            ),
            "best_effort_location_note": merged_facts.location_note,
            "inside_building": merged_facts.inside_building,
            "has_sub_location": bool(merged_facts.sub_location),
        },
    }


def build_pioneer_fact_ledger_record(example: dict[str, Any]) -> dict[str, Any]:
    payload = FactLedgerTrainingExample.model_validate(example)
    return {
        "schema_version": FACT_LEDGER_SCHEMA_VERSION,
        "messages": [
            {"role": "system", "content": FACT_LEDGER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "caller_turn": payload.caller_turn,
                        "prior_facts": payload.prior_facts.model_dump(),
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "merged_facts": payload.merged_facts.model_dump(),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
