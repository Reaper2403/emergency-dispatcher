# Stack Docs Index

Last updated: 2026-04-25

Purpose: lean index for the current hackathon scope.

Current focus:

- `Gradbot + ai-coustics + Aikido`
- `Gradium` as the core voice provider path
- `telli` optional later
- `GLiNER2`, `Tavily`, and `Entire` deferred for now

## Read Order

1. [NEXT_3_HOURS.md](/Users/ashutoshchatterjee/Documents/Hackathon/NEXT_3_HOURS.md)
2. [STACK_GAP_TRACKER.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_GAP_TRACKER.md)
3. [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md)
4. [SPONSOR_QUESTION_BANK.md](/Users/ashutoshchatterjee/Documents/Hackathon/SPONSOR_QUESTION_BANK.md)

## What Each File Is For

| File | Use it for | When to open it |
| --- | --- | --- |
| [NEXT_3_HOURS.md](/Users/ashutoshchatterjee/Documents/Hackathon/NEXT_3_HOURS.md) | Lean execution plan for the next milestone | Right now |
| [STACK_GAP_TRACKER.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_GAP_TRACKER.md) | Live checklist of unresolved blockers and assumptions | Before talking to reps and immediately after |
| [SPONSOR_QUESTION_BANK.md](/Users/ashutoshchatterjee/Documents/Hackathon/SPONSOR_QUESTION_BANK.md) | Exact questions to ask each sponsor | When you have a rep in front of you |
| [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md) | Verified knowns from official docs, plus remaining unknowns | When coding, debugging, or validating assumptions |
| [HACKATHON_PLAN_3HR_INCREMENTS.md](/Users/ashutoshchatterjee/Documents/Hackathon/HACKATHON_PLAN_3HR_INCREMENTS.md) | Build sequence and timeboxed execution plan | During the weekend rollout |

## Active Stack

Core:

- `Gradbot`
- `ai-coustics`
- `Gradium`

Optional integration layer:

- `LiveKit`
- `telli`

Prize / differentiation layer:

- `Aikido`
- `Entire`
- `Fastino / Pioneer / GLiNER2`

Optional helpers:

- `Tavily`
- `Lovable`
- `Google DeepMind temporary account`

## Priority Order For Sponsor Conversations

1. `ai-coustics`
2. `Gradium`
3. `telli`
4. `Fastino / Pioneer`
5. `Entire`
6. `Aikido`
7. `Google DeepMind`
8. `Tavily`
9. `Lovable`

Why this order:

- `Gradbot`, `ai-coustics`, and `Gradium` determine whether the core demo works
- `telli` is only important if we keep telephony / contact / KB integration in scope
- `Aikido` is the only side prize we care about in the immediate scope
- `Aikido` is low-risk and should be confirmed quickly
- everything else is deferred

## Fast Lookup

If you need:

- Gradbot / Gradium demo setup:
  - open [NEXT_3_HOURS.md](/Users/ashutoshchatterjee/Documents/Hackathon/NEXT_3_HOURS.md)
- core sponsor / integration blockers:
  - open [STACK_GAP_TRACKER.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_GAP_TRACKER.md)
- call control, phone numbers, contacts, KB, or post-call CRM updates:
  - open [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md) and jump to `telli`
- realtime STT, TTS, Gradium voices, or websocket contracts:
  - open [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md) and jump to `Gradium`
- audio enhancement model settings, LiveKit plugin behavior, or SDK constraints:
  - open [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md) and jump to `ai-coustics`
- exact rep questions:
  - open [SPONSOR_QUESTION_BANK.md](/Users/ashutoshchatterjee/Documents/Hackathon/SPONSOR_QUESTION_BANK.md)
- what we still do not know:
  - open [STACK_GAP_TRACKER.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_GAP_TRACKER.md)
- the safest default assumption when docs are incomplete:
  - open [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md) and look for `Default assumption`

## Current Hard Blockers

These are the highest-value unknowns to resolve first:

1. `Gradium`: Gradbot access path and fastest valid setup
2. `ai-coustics`: hackathon SDK key path and recommended model / parameter for our use case
3. `Aikido`: repo hookup and screenshot proof
4. `telli`: only whether it is worth keeping later

## Current Default Assumptions

Until a sponsor contradicts them, use these:

- `Gradbot`: use it first for the voice loop
- `ai-coustics`: start with `Quail Voice Focus` / `QUAIL_VF_L` and `enhancement_level=0.8`
- `Gradium`: assume it is the voice-model backend under the Gradbot path
- `Aikido`: connect early and capture one screenshot
- `telli`: ignore for the next 3 hours unless it becomes trivially useful

## Maintenance Rule

When a sponsor answers something important:

1. Update [STACK_GAP_TRACKER.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_GAP_TRACKER.md)
2. Update [STACK_INTERNAL_REFERENCE.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_INTERNAL_REFERENCE.md)
3. If the answer changes sequencing, update [HACKATHON_PLAN_3HR_INCREMENTS.md](/Users/ashutoshchatterjee/Documents/Hackathon/HACKATHON_PLAN_3HR_INCREMENTS.md)
