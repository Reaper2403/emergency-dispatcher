from __future__ import annotations

from pathlib import Path
from typing import Any

import gradbot

from .dispatch_tools import build_gradbot_tool_defs

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = REPO_ROOT / "prompts" / "dispatcher_system_prompt.md"


def load_dispatch_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _adaptive_turn_settings(interrupt_count: int) -> tuple[float, float]:
    active_interrupts = max(0, interrupt_count)
    flush_duration_s = min(1.25 + (0.22 * active_interrupts), 2.05)
    silence_timeout_s = min(6.5 + (1.2 * active_interrupts), 11.5)
    return flush_duration_s, silence_timeout_s


def _format_triage_context(triage_context: dict[str, Any] | None) -> list[str]:
    if not triage_context:
        return []
    merged = triage_context.get("merged_triage_state") or {}
    latest_delta = triage_context.get("latest_triage_delta") or {}
    stt_rescue = triage_context.get("stt_rescue")
    conversation_focus = triage_context.get("conversation_focus") or {}
    constraint_mode = merged.get("constraint_mode") or latest_delta.get("constraint_mode")
    lines = [
        "",
        "Live triage packet:",
        f"- issue_type: {merged.get('issue_type')}",
        f"- caller_safe: {merged.get('caller_safe')}",
        f"- location: {merged.get('location')}",
        f"- victim_count: {merged.get('victim_count')}",
        f"- victim_breathing: {merged.get('victim_breathing')}",
        f"- victim_bleeding: {merged.get('victim_bleeding')}",
        f"- victim_conscious: {merged.get('victim_conscious')}",
        f"- severity_score: {merged.get('severity_score')}",
        f"- human_required: {merged.get('human_required')}",
        f"- constraint_mode: {constraint_mode}",
        f"- address_in_utterance: {latest_delta.get('address_in_utterance')}",
        f"- next_question_field: {conversation_focus.get('next_question_field')}",
        f"- next_question_goal: {conversation_focus.get('next_question_goal')}",
        f"- location_search_allowed: {conversation_focus.get('location_search_allowed')}",
    ]
    if stt_rescue:
        lines.append(f"- rescue_text: {stt_rescue.get('corrected_transcript')}")
        lines.append(f"- rescue_repeat: {stt_rescue.get('ask_for_repeat')}")
        lines.append(f"- rescue_location_spelling: {stt_rescue.get('location_needs_spelling')}")
        lines.extend(
        [
            "",
            "Runtime rules:",
            "- use the triage packet as the source of truth unless the caller clearly corrects it",
            "- be brief, calm, and natural",
            "- ask one question only",
            "- if next_question_field is set, ask only for that field",
            "- do not ask a lower-priority question while a higher-priority field is still missing",
            "- if you ask about the caller, use second person like `Are you able to breathe properly?` or `Are you awake right now?`",
            "- if you ask about another person, use third person like `Is she breathing right now?` or `Is he awake right now?`",
            "- never ask `Are you conscious?` and never produce broken starts like `Is Are you`",
            "- prefer one relevant deterministic tool call before a follow-up when a hard fact just changed",
            "- use resolve_location_note first for landmarks, entrances, floors, rooms, or relative clues",
            "- use checklist_by_incident before deciding the next hard-fact question",
            "- use validate_address or lookup_address only after a searchable location clue lands",
            "- use nearby_context only after a stable place or address lands",
            "- use build_handoff_brief when facts stabilize or before ticket creation",
            "- use at most one tool before each spoken follow-up, except location flow may use address + nearby_context back to back",
            "- do not ask again for a fact already resolved by the triage packet or latest tool output",
            "- do not call a tool if it would only restate known information",
            "- before a slow location lookup or validation, say one short holding line so the caller is not left in silence",
            "- approved holding examples: `I'm locating and dispatching the nearest team now. Give me a moment.`, `Okay, I'm checking that location now.`",
            "- use only one holding line for the same wait",
            "- never call validate_address or lookup_address unless location_search_allowed is true",
            "- never geocode vague phrases like `middle of the street`, `inside the building`, `here`, or `at home`",
            "- if indoors, ask for floor, unit, entrance, stairwell, or building name before outside landmarks",
            "- respect constraint_mode exactly",
        ]
    )
    if constraint_mode == "single_question_only":
        lines.extend(
            [
                "",
                "Mode:",
                "- ask exactly one short direct question",
            ]
        )
    elif constraint_mode == "pre_arrival_priority":
        lines.extend(
            [
                "",
                "Mode:",
                "- stop broad information gathering",
                "- give immediate pre-arrival help or one binary confirmation only if it changes safety actions",
            ]
        )
    elif constraint_mode == "holding_pattern_only":
        lines.extend(
            [
                "",
                "Mode:",
                "- do not ask exploratory questions",
                "- keep the caller on the line",
                "- give at most one short safety instruction",
            ]
        )
    if stt_rescue:
        lines.extend(
            [
                "",
                "STT rescue guidance:",
                "- use rescue_text as the best current reading of the last caller turn",
            ]
        )
        if stt_rescue.get("ask_for_repeat"):
            lines.extend(
                [
                    "- start by saying you did not quite catch the last part",
                    "- ask the caller to repeat or confirm the unstable detail before moving on",
                ]
            )
        if stt_rescue.get("location_needs_spelling"):
            lines.extend(
                [
                    "- the unstable detail is the location",
                    "- ask for one road, landmark, or junction slowly",
                    "- ask the caller to spell the key word",
                ]
            )
    return lines


def _format_dispatch_context(dispatch_context: dict[str, Any] | None) -> list[str]:
    if not dispatch_context:
        return []
    lines = [
        "",
        "Live dispatch operations packet:",
        f"- serious_emergency: {dispatch_context.get('serious_emergency')}",
        f"- human_monitoring: {dispatch_context.get('human_monitoring')}",
        f"- monitor_name: {dispatch_context.get('monitor_name')}",
        f"- services_summary: {dispatch_context.get('services_summary')}",
    ]
    announcement_line = dispatch_context.get("announcement_line")
    if announcement_line:
        lines.append(f"- announcement_line: {announcement_line}")
    lines.extend(
        [
            "",
            "Dispatch operations rules:",
            "- if announcement_line is present, weave it into your next reply once, naturally and briefly",
            "- treat human_monitoring and service updates as operator-confirmed",
            "- do not repeat the same monitoring or ETA line after it has been delivered once",
            "- keep operations updates to one short sentence, then return to the caller's immediate need",
        ]
    )
    return lines


def _runtime_prompt(
    *,
    interrupt_count: int = 0,
    interruption_recovery: bool = False,
    triage_context: dict[str, Any] | None = None,
    dispatch_context: dict[str, Any] | None = None,
) -> str:
    prompt = load_dispatch_prompt()
    adaptive_lines: list[str] = []
    if interrupt_count > 0 or interruption_recovery:
        adaptive_lines = [
            "",
            "Adaptive turn-taking policy:",
            f"- interruption_count: {interrupt_count}",
            "- if the caller cuts in or you begin speaking over them, stop escalating the exchange",
            "- apologize briefly with: `Sorry, go ahead. Please repeat that last part.`",
            "- after apologizing, ask no new question in that turn",
            "- wait for the caller to finish before speaking again",
            "- after an interruption, prefer a longer pause before taking the next turn",
        ]
    if interruption_recovery:
        adaptive_lines.extend(
            [
                "",
                "Immediate recovery instruction:",
                "- a recent interruption just occurred",
                "- on your next turn, your first job is recovery, not triage",
                "- say: `Sorry, go ahead. Please repeat that last part.`",
                "- then wait for the caller to finish",
            ]
        )
    triage_lines = _format_triage_context(triage_context)
    dispatch_lines = _format_dispatch_context(dispatch_context)
    return prompt + "\n" + "\n".join(adaptive_lines + triage_lines + dispatch_lines)


def build_tool_defs() -> list[gradbot.ToolDef]:
    return [
        gradbot.ToolDef(
            name=name,
            description=description,
            parameters_json=parameters_json,
        )
        for name, description, parameters_json in build_gradbot_tool_defs()
    ]


def build_session_config(
    *,
    interrupt_count: int = 0,
    interruption_recovery: bool = False,
    triage_context: dict[str, Any] | None = None,
    dispatch_context: dict[str, Any] | None = None,
) -> gradbot.SessionConfig:
    voice = gradbot.flagship_voice("Emma")
    prompt = _runtime_prompt(
        interrupt_count=interrupt_count,
        interruption_recovery=interruption_recovery,
        triage_context=triage_context,
        dispatch_context=dispatch_context,
    )
    flush_duration_s, silence_timeout_s = _adaptive_turn_settings(interrupt_count)
    return gradbot.SessionConfig(
        voice_id=voice.voice_id,
        language=voice.language,
        assistant_speaks_first=False,
        instructions=prompt,
        silence_timeout_s=silence_timeout_s,
        flush_duration_s=flush_duration_s,
        tools=build_tool_defs(),
    )
