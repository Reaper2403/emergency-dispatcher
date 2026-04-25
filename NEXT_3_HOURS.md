# Next 3 Hours

Last updated: 2026-04-25

## Scope

Core path:

- `Gradbot`
- `ai-coustics`
- `Aikido`

Support:

- `Gradium` API key / voices / model config
- `LiveKit` only if the Gradbot path needs it

Deferred:

- `GLiNER2`
- `telli`
- `Tavily`
- `Entire`

## One-Line Architecture

`mic/browser -> ai-coustics -> Gradbot (STT + LLM loop + TTS/tool calls) -> one tool -> demo`

## Hour 1

- get `ai-coustics` key
- get `Gradium` key / Gradbot access path
- `pip install gradbot`
- run the simplest Gradbot voice demo locally
- confirm:
  - it hears
  - it replies
  - it runs in browser or local demo surface

Exit:

- base voice loop works end to end

## Hour 2

- add `ai-coustics` before Gradbot STT input
- add exactly one tool:
  - `lookup_address(location: str)` returning a stubbed response
- confirm:
  - noisy audio in
  - cleaned audio improves transcript visibly
  - tool call fires
  - agent responds with tool result

Exit:

- one noisy-to-tool-call demo works

## Hour 3

- record `3` noisy clips
- compare transcript output:
  - without ai-coustics
  - with ai-coustics
- save screenshots or short notes of the visible improvement
- connect repo to `Aikido`
- capture one clean Aikido screenshot

Exit:

- demo works
- noise improvement is visible
- one tool fires
- Aikido proof exists

## Hard Rules

- no `GLiNER2` in v1
- no `telli` integration in the first 3 hours unless the core loop is already stable
- no `Tavily` until the core demo is working
- skip `Entire`
- do not over-design the metric yet; visual transcript delta is enough for now

## What We Need To Learn Immediately

1. Is `Gradbot` the fastest valid path for Gradium at this event?
2. How should `ai-coustics` be inserted before Gradbot in the simplest way?
3. What exact demo surface is fastest: local browser, Gradbot demo UI, or LiveKit console/playground?

## Next Layer After This

Append only after the 3-hour milestone is done:

1. real metric / WER bench
2. structured extraction
3. `telli` CRM/contact integration
4. `Tavily` live lookup
5. polish and pitch
