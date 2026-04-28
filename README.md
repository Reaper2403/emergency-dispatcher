# Emergency Dispatcher

Realtime emergency-dispatch demo for noisy environments.

Originally built during a hackathon, this repo is the working system that the later SLM + LLM grounding playbook was extracted from.

The architectural pattern this project converged on — fast LLM voice lane plus slow SLM grounding lane around a shared ledger — is generalized in a separate playbook: [Reaper2403/slm-llm-grounding-playbook](https://github.com/Reaper2403/slm-llm-grounding-playbook).


https://github.com/user-attachments/assets/f2ee3c60-c74e-4e77-944c-5098a3172fef



The project combines:
- `ai-coustics` for live input enhancement
- `Gradbot + Gradium` for the voice loop
- `Deepgram` as a continuous backend STT cross-check
- `FastAPI` for the demo server and session APIs
- a triage layer that can run in `heuristic`, `llm`, or `slm` mode
- local and Pioneer-oriented dataset tooling for the SLM path

## What Exists Today

### Live demo
- browser-based dispatch console at `/demo`
- live caller / dispatcher transcript streams
- operator-facing handoff desk with severity display and dummy takeover button
- live map and tool timeline
- persisted sessions under `runs/sessions/`

### Runtime pipeline
- mic audio is resampled and sent as PCM
- `ai-coustics` enhances the live input path
- `Gradium` remains the low-latency live voice loop
- finalized utterances are synced back to the backend
- `Deepgram` continuously compares finalized caller turns and can become the canonical backend transcript provider for the session
- triage state is merged turn by turn and fed into the LLM prompt

### Triage / SLM groundwork
- stable triage contract in `src/emergency_dispatcher/triage.py`
- modes:
  - `heuristic`
  - `llm`
  - `slm`
- SLM data-generation scripts for:
  - dispatch guidance
  - fact-ledger style evidence tracking
- Pioneer-ready decoder dataset export scripts

## Current Runtime Direction

The project now supports two practical live modes:
- `LLM only`
- `SLM + LLM`

What we learned from repeated live calls:
- `LLM only` is currently the smoothest voice path
- `LLM only` can sound natural and recover from noisy turns well
- `LLM only` plateaus on grounding, consistency, and deterministic fact handling
- the next step is a narrower `SLM + LLM` split where the SLM owns hard facts and the LLM owns delivery and judgment

That split is now the intended architecture:
- `SLM / deterministic ledger`: hard facts, location certainty, issue cues, victim count, breathing / bleeding / trapped status
- `LLM`: calm questioning, ambiguity handling, empathy, and spoken instructions
- `server tools`: location resolution, nearby response bases, dispatch simulation, and handoff/ticket generation

## Repo Layout

```text
src/emergency_dispatcher/
  server.py             FastAPI app + websocket voice session
  gradbot_adapter.py    runtime prompt + tool definitions
  dispatch_tools.py     address, priority, and ticket tools
  enhanced_audio.py     ai-coustics live/audio artifact handling
  stt_rescue.py         Deepgram/Soniox rescue and backend transcript selection
  triage.py             triage engine interface + state merge + runtime prompt packet
  slm_guidance.py       guidance-style SLM schema and helpers
  slm_fact_ledger.py    fact-ledger schema and helpers
  berlin_location_lexicon.py  Berlin lexicon helpers for data generation

frontend/
  index.html            live dispatch console
  app.js                browser session logic + operator desk
  review.html           session review page
  review.js             review UI
  styles.css            shared frontend styling

scripts/
  generate_dispatch_training_data.py
  generate_slm_guidance_training_data.py
  generate_slm_fact_ledger_training_data.py
  prepare_* / finalize_* / export_* helpers for dataset workflows

data/
  emergency_scenarios.json
  schema/               checked-in schema snapshots

tests/
  pytest suite for tools, rescue, triage, schemas, and routes
```

## Required Setup

Use Python `3.13`.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Create `.env` from [.env.example](./.env.example).

Minimum for the live app:

```env
GRADIUM_API_KEY=...
AI_COUSTICS_API_KEY=...
OPENAI_API_KEY=...
OPENAI_MODEL=...
DEEPGRAM_API_KEY=...
```

Optional / advanced:

```env
SONIOX_API_KEY=...
TRIAGE_API_KEY=...
TRIAGE_DECODER_MODEL=...
TRIAGE_GLINER_MODEL=...
GOOGLE_MAPS_API_KEY=...
GOOGLE_CLOUD_PROJECT=...
```

Important defaults already supported:
- `TRIAGE_ENGINE=heuristic|llm|slm`
- `LIVE_DISPATCH_MODE=slm|llm_only`
- `STT_RESCUE_CONTINUOUS_COMPARE=true`

## Run The App

Use this while actively testing calls:

```bash
cd path/to/repo
source .venv/bin/activate
PYTHONPATH=src uvicorn emergency_dispatcher.server:app --host 127.0.0.1 --port 8001
```

Avoid `--reload` while generating datasets inside this repo. The file watcher can restart the server mid-call.

## Smoke Checks

Core provider check:

```bash
cd path/to/repo
source .venv/bin/activate
PYTHONPATH=src python -m emergency_dispatcher.smoke
```

Test suite:

```bash
cd path/to/repo
source .venv/bin/activate
PYTHONPATH=src pytest -q
```

## Current Tool Surface

The current live stack is intentionally split between:

### LLM-triggered tools
- `resolve_location_note`
- `checklist_by_incident`
- `validate_address`
- `lookup_address`
- `nearby_context`
- `build_handoff_brief`
- `create_incident_ticket`

### Server-driven deterministic tools
- `plan_response_services`
- `lookup_response_bases`
- `simulate_dispatch_services`

The important design choice is that service planning, dispatch theatrics, and nearby-base resolution should not depend on the LLM remembering to do them.

## LLM-Only Plateau

The current `LLM only` path is good enough to demo:
- low-latency voice interaction
- noisy-call turn recovery
- believable dispatcher tone
- map pinning and dispatch theatrics when the location path lands

But it still plateaus on:
- exact location confirmation and correction handling
- consistent caller-vs-third-person medical phrasing
- duplicate / awkward question forms under pressure
- deterministic fact carry-forward across fragmented STT turns
- knowing when to trust, reject, or defer a location candidate

That is why the next phase is not “make the LLM smarter.”
It is:
- keep the voice loop light
- keep deterministic tools lean
- move hard-fact grounding into the fact-ledger SLM path

## Data Generation Workflows

### Local guidance dataset generation

Requires a local `Ollama` server.

Start Ollama:

```bash
/opt/homebrew/bin/ollama serve
```

Generate a small validation batch first:

```bash
cd path/to/repo
source .venv/bin/activate
python -u scripts/generate_slm_guidance_training_data.py --count 50
```

### Fact-ledger dataset generation

```bash
cd path/to/repo
source .venv/bin/activate
python -u scripts/generate_slm_fact_ledger_training_data.py --count 50
```

### Pioneer export helpers

Use the `prepare_*`, `finalize_*`, and `export_*` scripts in [scripts](./scripts) once the local sample quality looks good.

## Current Documentation

The repo keeps only the active markdown docs:
- [README.md](./README.md): setup, architecture, runtime modes, and workflows
- [prompts/dispatcher_system_prompt.md](./prompts/dispatcher_system_prompt.md): active dispatcher runtime instructions

## Main Known Limits

- `LLM only` is smoother than the current `SLM + LLM` path, but it still tops out on factual grounding
- location flow is better than before, but still not yet a fully strict state machine
- service ETAs and dispatch states are demo-safe operator theatrics, not real CAD/AVL dispatch data
- `Soniox` is wired but not yet as trustworthy as `Deepgram`
- the human-takeover button is currently presentation-only
- the next serious quality step is the fact-ledger `SLM + LLM` path, not more prompt growth in `LLM only`
