# Frontline VoiceOS — 3-Hour Incremental Plan

Current note:

- for the immediate milestone, use [NEXT_3_HOURS.md](/Users/ashutoshchatterjee/Documents/Hackathon/NEXT_3_HOURS.md)
- this file is now the append-after-v1 plan, not the first thing to execute

**Goal:** at the end of every 3-hour block you have something *demonstrable*. If we run out of time at any checkpoint, we can still walk on stage with the previous one.

**Target stack:** `Gradium + ai-coustics + LiveKit` (main) + `Aikido` (free) + optional `telli` integration + `Entire` (functional) + `Pioneer/GLiNER2` (technical edge). Tavily/Lovable optional.

**Total budget assumed:** Saturday 10:00 → Sunday 14:00 = ~28h. Sleep 6h. Submission deadline Sunday 14:00.

---

## Block 0 — Hour 0 (Saturday 10:00–10:30, before kickoff)

This is during opening / matchmaking. Do **before** code starts.

- [ ] Three people get LiveKit Cloud accounts (free tier). Pick one project, share API key in private channel.
- [ ] One person creates Aikido account, connects the GitHub repo (read-only). Run a baseline scan immediately so we can compare a "before / after" later if we want a stronger Aikido story.
- [ ] One person finds the **telli sponsor rep** in person and gets:
  - API key
  - A test phone number that can place outbound calls
  - Confirmation of which scheduling / call-control endpoint is open for the event
  - Confirmation of what counts as valid telli usage now that telli is not supplying the core models
- [ ] One person finds the **Gradium sponsor rep** and gets:
  - API key / credits
  - Confirmation whether we should use Gradium for `STT`, `TTS`, or both
  - Recommended `LiveKit` integration path
  - Recommended default voice / model / language for the demo
- [ ] One person finds the **ai-coustics sponsor rep** and gets:
  - SDK key (theirs is normally a 30-day trial via developer platform; sponsor key avoids the business-email gate)
  - Confirmation of which model to showcase: `QUAIL_VF_L` (single-speaker isolation) or `QUAIL_L` (multi-speaker scenes). For our "noisy real-world calls" story, default is `QUAIL_VF_L` with `enhancement_level=0.8`.
- [ ] Find the **Entire rep** and ask point-blank: "what's the minimum integration that qualifies, and is there a sample / SDK we should use?" Don't assume — their public docs are thin.
- [ ] Find **Fastino/Pioneer rep** and confirm the fastest valid fine-tuning path, expected training time, and whether teams get credits or queue priority. We already know off-the-shelf GLiNER is not enough for the prize.

**Exit criterion for Block 0:** every API key in hand, every sponsor question answered. If a key is missing at 10:30, that integration is on the chopping block.

---

## Block 1 — Hours 0–3 (Sat 10:30–13:30): Bare voice loop works

**Outcome at end of block:** we can speak to the agent in browser or terminal, it transcribes us, and replies. **No noise handling, no ML, no UI.** Just: voice in → voice out.

### Track A — Voice (2 people)
- LiveKit Agents Python starter, run `console` mode first (works in terminal, no telephony needed). Default pipeline: `Gradium STT + chosen LLM + Gradium TTS`.
- Once console works, switch to `dev` mode and connect via the LiveKit playground in browser — this is the demo surface.
- If the telli rep gave us useful inbound/outbound phone access: wire LiveKit's SIP integration to the telli number. If not, fall back to **playground demo only** — judges accept this.

### Track B — Repo + Aikido (1 person)
- Repo created on GitHub, README skeleton, Aikido connected, baseline scan screenshot saved as `aikido_baseline.png`. Done. Move on to Track A or C.

### Track C — Bench rig (1 person, can be the same person who finished Aikido)
- Make a small "noise injector": take a clean reference audio (we record ourselves saying 5 fixed sentences) and mix in: café noise, traffic, second-speaker, music. WAV files saved to `bench/noisy/` and `bench/clean/`.
- This is the data we'll use for the **audio intelligence metric**. We need this *built before* hour 6 or the metric story falls apart.

**Demo at end of Block 1:** "watch us speak to it in the browser, it replies." That's a baseline good enough to walk on stage with — it's not winning yet, but it exists.

---

## Block 2 — Hours 3–6 (Sat 13:30–16:30): Noise becomes the story

**Outcome:** ai-coustics is integrated, and we have a side-by-side WER number on our bench data. **This is the moment we have a "main track entry."**

### Track A — Plug ai-coustics into LiveKit (1 person)
The integration is essentially:

```python
from livekit.plugins import ai_coustics
from livekit.agents import AgentSession, RoomIO

session = AgentSession(
    vad=ai_coustics.VAD(),
    # ... your STT/LLM/TTS
)

await session.start(
    agent=Assistant(),
    room=ctx.room,
    room_options=RoomIO.RoomOptions(
        audio_input=RoomIO.AudioInputOptions(
            noise_cancellation=ai_coustics.audio_enhancement(
                model=ai_coustics.EnhancerModel.QUAIL_VF_L,
                model_parameters=ai_coustics.ModelParameters(enhancement_level=0.8),
            ),
        ),
    ),
)
```

Run the same agent twice — once with the noise cancellation block, once without. That's the A/B.

### Track B — Run the bench (1 person)
- Pipe each `bench/noisy/*.wav` file through:
  - Path 1: STT directly (baseline)
  - Path 2: ai-coustics enhancement → STT
- Compute WER against the clean reference transcripts using `jiwer` (`pip install jiwer`).
- Save results to a small JSON: `{file, wer_baseline, wer_enhanced, wer_reduction_pct}`.
- **This JSON is the audio intelligence metric.** Display it in the demo.

### Track C — Optional telli context (1 person)
- Use `POST /v2/contacts` to seed a few demo contacts (the "caller" the agent expects to hear from). Confirm that `GET /v2/external/contacts/{externalId}` lookup returns them.
- Stub a Knowledge Base with one PDF of made-up policy info for our chosen vertical (see "framing" below).

### Pick the framing here, lock it in:
- **Roadside assistance** — caller in noisy car/highway, agent extracts location + vehicle + issue, dispatches.
- **Field service incident** — technician on noisy site reports equipment fault.
- **Property emergency intake** (good if you want the Buena angle as bonus) — tenant calls about a leak/break-in, noisy hallway / street.

Default recommendation: **roadside assistance**. It makes "noisy environment" the *premise*, not a gimmick, and Bose-headphones judges will get it instantly.

**Demo at end of Block 2:** "here's a noisy roadside call. Without ai-coustics, the agent thinks the user's name is 'Tarn' and the car is a 'Toyoga'. With ai-coustics, name and vehicle come through clean. We measured a 32% WER reduction on our bench." That's a winning main-track demo on its own.

---

## Block 3 — Hours 6–9 (Sat 16:30–19:30, dinner happens at 18:30): Confidence + extraction

**Outcome:** the agent has a **confidence signal** and uses it to behave smarter. This is what separates "noise filter demo" from "Frontline VoiceOS."

### Track A — GLiNER2 extraction (1 person, ML-leaning)

```bash
pip install gliner2
```

```python
from gliner2 import GLiNER2

extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")

schema = (extractor.create_schema()
    .structure("incident")
    .field("caller_name", dtype="str")
    .field("vehicle_make", dtype="str")
    .field("vehicle_model", dtype="str")
    .field("location", dtype="str")
    .field("issue_type", dtype="str")
)

# After each user utterance:
result = extractor.extract(transcript, schema)
```

Two things to log per utterance:
1. The extracted fields.
2. **A confidence score per field.** GLiNER2 returns model probabilities; if not directly exposed in the API call you use, you can re-run with the same text and check whether it stably produces the same answer across 3 runs (proxy confidence). Easier: also classify the same text with `classify_text` for `{"audio_quality": ["clear","muffled","unintelligible"]}` and combine those signals.

Frame it to judges as: "Pioneer-family GLiNER2 model running on CPU, replacing what would otherwise be a generic LLM call. Fast, cheap, schema-locked output."

Kick off a Pioneer fine-tuning run in parallel **as soon as block 3 starts** if we still want the side prize. Off-the-shelf GLiNER is useful for prototyping but does not satisfy the intended challenge bar. Use the fine-tuned model as a strict upgrade in block 5 or 6 if it lands. Don't block on it.

### Track B — Trust score + agent behavior (1 person)

Define one number per turn: `trust = w1 * (1 - wer_estimate) + w2 * extraction_confidence + w3 * vad_certainty`. Pick weights, hardcode, move on.

Behavior rules:
- `trust > 0.8` → commit fields to telli contact if telli is in scope, then proceed.
- `0.5 < trust ≤ 0.8` → agent re-asks: "Just to confirm, did you say a Toyota Corolla?"
- `trust ≤ 0.5` → **escalation flag set.** This is the hook for Entire.

### Track C — Optional telli wiring (1 person)
- If telli remains in scope, on `trust > 0.8` events, `PATCH /v2/contacts/{id}` with extracted fields.
- If telli remains in scope, after call ends write a structured summary to telli's contact properties. This is the "post-call CRM update" story.

**Demo at end of Block 3:** "the agent isn't just denoising — it knows when *it's* uncertain. Watch: when noise spikes, the trust score drops and the agent re-asks. When it's clean, it commits to the CRM."

---

### Sleep window: 19:30–01:30 or thereabouts. **Don't push through.** A clean demo at 13:00 Sunday beats a broken pipeline at 14:00.

---

## Block 4 — Hours 9–12 (Sun 01:30–04:30 if you push, otherwise Sun 06:00–09:00): Human escalation (Entire)

**Outcome:** when trust drops below threshold, a human dashboard lights up showing live transcript + extracted fields + a "take over" button.

### Implementation (whichever stack the Entire rep blesses)

Default if the rep gave you nothing usable: build a **plain web dashboard** with:
- WebSocket subscription to your LiveKit room's transcription events.
- Live-updating cards: caller name, vehicle, location, issue, trust score (color-coded).
- Big red **"Take over"** button that mutes the agent and joins a human into the LiveKit room.
- If telli remains in scope, add an "Approve & dispatch" green button that PATCHes the telli contact and ends.

Frameworks (in order of speed): **Lovable Pro** (use the free code) → React + LiveKit JS SDK → plain HTML+WebSocket. Lovable will get you a polished UI in ~1 hour; raw React takes ~2-3.

This dashboard *is* your "Entire integration." When the rep evaluates: show trust drop → dashboard alerts → human takes over → call resolves. That's the wow moment.

**Demo at end of Block 4:** the full "AI when possible, human when needed" story works end to end. **At this point you are competitive across telli/ai-coustics + Aikido + Entire.**

---

## Block 5 — Hours 12–15 (Sun 09:00–12:00): Polish + the metric slide

**Outcome:** the demo is *rehearsed*, not just functional. The metric is presentable.

- [ ] Run the bench from Block 2 again on the *current* pipeline (post-extraction). Now you have **three numbers** to show: WER baseline, WER with ai-coustics, task completion rate (% of calls where all required fields ended `trust > 0.8` without human takeover). Task completion is the *real* metric judges remember.
- [ ] Make a single chart: bar chart, three bars, big numbers. This is your money slide.
- [ ] Write the pitch as a tight 3-minute story:
  1. **Hook (20s):** "voice agents fail in the real world because they fail at hearing. Try having one understand a tow request from the side of the autobahn."
  2. **Problem (20s):** play a 5-second clip of unenhanced noisy audio + the gibberish transcript.
  3. **What we built (60s):** demo the full loop — noisy audio → ai-coustics → Gradium STT/TTS → trust/extraction layer, with the trust score visible.
  4. **The wow (30s):** trigger the noisy edge case → trust drops → Entire dashboard alerts → human takes over → resolution.
  5. **Numbers (30s):** the chart, the WER reduction, the task completion lift.
  6. **Stack (20s):** name-check Gradium, ai-coustics, Pioneer/GLiNER2, Entire, Aikido, and telli only if we actually used it. Show the Aikido security report screenshot.
- [ ] Re-run Aikido scan, capture final screenshot.
- [ ] Record a backup video of the working demo. **Always record a backup.** Demo gods are cruel.

---

## Block 6 — Hours 15–18 (Sun 12:00–14:00): Submission + buffer

- [ ] Submit project. Include for each prize:
  - **Main track:** repo link, demo video, the metric chart, paragraph on why it works in the wild.
  - **Aikido:** repo connected ✓, screenshot included ✓.
  - **Pioneer:** name the GLiNER2 model used, link to the schema, explain "we replaced a generic LLM extraction call with a 205M-param schema-driven model running on CPU." If a Pioneer fine-tune run completed, show before/after accuracy.
  - **Entire:** screenshot of the dashboard, paragraph on the takeover flow.
- [ ] Buffer hour for the inevitable "wait, the demo broke" panic.
- [ ] **14:00 deadline.**

---

## What we drop if we're behind

In strict order:

1. **Tavily** — never essential, only adds noise.
2. **Lovable** — fall back to plain React.
3. **Pioneer fine-tuning** — drop the Pioneer prize path and keep base GLiNER2 only for internal prototyping if helpful.
4. **telli integration entirely** — keep the core demo on `LiveKit + ai-coustics + Gradium`.
5. **Telephony / SIP** — use LiveKit playground browser-based audio. Judges accept this.
6. **Entire dashboard polish** — keep functionality, drop the prettiness.
7. **GLiNER2 entirely** — use a single LLM call for extraction. We lose the Pioneer prize but main track survives.

We never drop ai-coustics integration or the WER metric. Those are the main track.

---

## Realistic prize-stack expectation

If everything works:
- Main track (core voice stack): **strong contender** if the noise metric is real and the demo is clean.
- Aikido (1000€): **near-certain** if the screenshot is in the submission.
- Entire ($1000 cards + consoles): **competitive** assuming integration meets their bar.
- Pioneer (Mac Mini value, 700€): **only realistic if a fine-tune run lands or the sponsor blesses a minimal specialized-training path**.

Realistic expected value: 1 prize is very likely, 2 is the goal, 3+ is upside.

The thing that makes us actually *win* main track isn't the stack — it's the **task completion metric on real noisy data**. Judges have seen ten "I built a voice agent" demos by 15:00 Sunday. The team that walks up and says "we measured it, here's the chart, here's why this is the only one of these that would work in production" wins.

---

## Open questions to chase early

1. What is the fastest correct `Gradium + LiveKit` integration path for the event? *Ask at hour 0.*
2. Does telli's current API expose enough telephony / contact value to be worth keeping in scope? *Ask the rep at hour 0.*
3. What does Entire actually require to count as "used"? Their public surface is too thin to plan from. *Sponsor-led, not docs-led.*
4. How long do Pioneer training jobs take right now, and what exact artifact do they want for prize qualification? *Ask early — determines whether to start a fine-tune run.*
5. ai-coustics SDK key: edge/local SDK or LiveKit cloud-hosted plugin? Both work; cloud is simpler. *5-minute conversation with their rep.*
