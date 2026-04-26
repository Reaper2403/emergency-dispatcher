# Progress

Current repo status as of April 26, 2026.

## What Is Working

- Browser demo at `/demo`
- Session review page at `/review`
- Live voice loop with `Gradium + Gradbot`
- Live input enhancement with `ai-coustics`
- Continuous backend STT comparison with `Deepgram`
- Address validation and lookup with Google-first geocoding fallback
- Incident priority assignment and ticket creation
- Persisted session logs and saved audio artifacts under `runs/`
- Triage layer that can run in `heuristic`, `llm`, or `slm` mode
- Local dataset-generation scripts for the SLM path

## What Improved Recently

- Removed stale planning docs so the repo only keeps active documentation
- Rewrote `README.md` around the current architecture instead of the original hackathon plan
- Distilled `learning.md` into a shorter failure-mode and lessons doc
- Added finalized-utterance handling so the backend stops reasoning over raw partial transcript shards
- Added continuous backend STT comparison so `Deepgram` can outperform `Gradium` on noisy finalized turns
- Improved presentation with an operator-facing summary, severity display, and dummy human-takeover surface

## What Is Still Weak

- Dialogue policy is still rough on critical calls
- The agent can still sound repetitive even when STT quality is acceptable
- Location handling is better, but the confirmation ladder is still partly prompt-driven
- `Soniox` is wired but not dependable enough to be part of the main story
- Human takeover is still presentation-only, not a real parallel handoff workflow
- The fine-tuned SLM is not in the runtime yet

## Current Open Items

1. Add stricter dialogue-mode switching:
   - normal triage
   - clarification
   - holding / handoff
2. Tighten location confirmation into a backend state machine:
   - pin
   - read back
   - ask landmark
   - ask spelling if needed
3. Reduce premature ticket creation and rely more on stable merged triage state
4. Bring the trained SLM into the existing triage socket once the dataset is ready
5. Run a clean hosted phone test after the conversation policy is more stable

## Documentation Map

- `README.md`: setup, architecture, run commands, workflows
- `progress.md`: current repo and product status
- `learning.md`: distilled lessons and failure modes
- `prompts/dispatcher_system_prompt.md`: active dispatcher runtime instructions
