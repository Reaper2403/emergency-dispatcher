# Learning

Short version: the project is no longer blocked by basic setup. The remaining problems are mostly about `policy`, `state`, and `presentation`, not whether the stack can run at all.

## What We Know

### 1. STT quality is necessary but not sufficient
- better transcripts help, but they do not automatically produce better dispatcher behavior
- the system can still sound chaotic if it reacts to partial state, stale state, or the wrong dialogue mode

### 2. Finalized turns matter more than raw partials
- partial transcript shards caused repeated filler, bad triage updates, and broken rescue behavior
- the backend should reason over finalized utterances, not every transient chunk

### 3. Deepgram is the practical fallback right now
- `Deepgram` is the only backup STT that has consistently helped in this repo
- `Soniox` is not yet reliable enough in the current integration path
- continuous backend comparison is a safer strategy than trying to hot-swap the live voice loop

### 4. The location path needs hard structure
- location got much better once geocoding, confirmation readback, and Google fallback were added
- the system should still ask in a strict order:
  - try to pin
  - if no pin, ask for one landmark or road sign
  - if the name sounds unstable, ask the caller to spell it
- location and tool outputs must be JSON-serializable; we already hit one real crash from a circular geocoder result

### 5. The agent still needs better mode switching
- once the backend knows a case is critical and not suitable for autonomous handling, the conversation should narrow sharply
- repeating triage questions after handoff state is known is worse than asking fewer questions
- the missing piece is a stronger runtime shift between:
  - normal triage
  - clarification
  - holding / handoff behavior

### 6. The SLM belongs before the LLM, not instead of it
- best fit:
  - `STT -> SLM triage/extraction -> runtime rules -> LLM -> tools / phrasing`
- let the SLM own structured extraction and control hints
- let the LLM own next-question selection, tool usage, and short dispatcher wording

### 7. Presentation matters
- the operator desk, human-ready summary, and visible severity signal are not polish-only
- they make the system understandable even when the model is imperfect
- a human handoff brief is much more useful than raw JSON during demos

## Biggest Remaining Risks

- the dialogue policy is still rough on long, emotional calls
- the current location flow is better, but still not a strict backend state machine
- early ticket creation can still happen before the incident is fully stable
- the live handoff / takeover behavior is still UI-first, not operationally wired

## Practical Rule Going Forward

When in doubt:
- reduce LLM freedom
- move ambiguity into tools or structured state
- prefer one good operator-facing artifact over another speculative model behavior tweak
