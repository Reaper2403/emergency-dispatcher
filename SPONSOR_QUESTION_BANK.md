# Sponsor Question Bank

Last updated: 2026-04-25

Purpose: these questions are intentionally focused on gaps the public docs do not answer clearly. Do not waste sponsor time re-asking things already documented unless we hit a contradiction.

Current scope:

- ask `Gradium`, `ai-coustics`, and `Aikido` first
- ask `telli` only if we still want it after the first voice demo works
- defer `Entire`, `Tavily`, and most other side tracks for now

Use this order when time is tight:

1. ask the `Must Ask` questions only for the current-scope sponsors
2. write the answer in [STACK_GAP_TRACKER.md](/Users/ashutoshchatterjee/Documents/Hackathon/STACK_GAP_TRACKER.md)
3. ask `Important If Time`
4. ignore `Nice To Have` if the rep is busy

## 1. telli

### Must Ask

1. We heard telli is not providing the core voice models. Can you confirm what telli is intended to provide for hackathon teams: telephony, contacts, KB, workflows, CRM, or something else?
2. If we use external STT/TTS models and only use telli for `contacts + KB + telephony/context`, does that still count as valid telli usage for judging?
3. Do hackathon teams get a test `API key`, test phone number, and a safe sandbox for outbound/inbound calling?
4. Is there a public or sponsor-enabled endpoint for `programmatic outbound call placement`? If yes, what is it exactly?
5. Is there a public or sponsor-enabled endpoint for `scheduling calls` directly over API, or is that only available through UI / n8n today?
6. Are there `webhooks` for call outcomes, transcripts, recordings, voicemail, or call status changes? If yes, where are the docs?
7. Can we `retrieve transcripts or recordings` over API for our own evaluation pipeline?
8. Do you have a `recommended sample workflow` or starter repo for the event?

### Important If Time

1. Are there any `rate limits`, concurrency limits, or account-level quotas we should know about?
2. Are `contact property definition` create/update endpoints available and enabled for our account?
3. Can we update contact properties during a live call, or should updates happen only post-call?
4. Is there a `call status` event model we can rely on for a demo?
5. Can telli numbers be used with `LiveKit` or SIP in a documented way for the event?
6. Are there any restrictions around `country`, `phone number geography`, or `verified caller ID` for hackathon use?
7. Can we access `live monitoring` data programmatically?
8. Is there an official way to attach or update a `Knowledge Base` programmatically, or is it UI-only?
9. If we use only one agent and one KB, are there any practical limits on KB update timing or indexing delay during the event?

### Nice To Have

1. Which call metrics matter most to your team when judging?
2. Do you care more about `human-likeness`, `task completion`, or `ops integration`?
3. What is the cleanest telli demo you have seen from a hackathon team?
4. Which features do teams usually overcomplicate and should skip?

## 2. ai-coustics

### Must Ask

1. What is the exact `hackathon access path` for SDK keys? Sponsor key, normal dashboard signup, or pre-issued credentials?
2. For our use case, which model do you want us to showcase: `QUAIL_VF_L` or `QUAIL_L`?
3. For a noisy single-caller voice-agent demo, do you agree that `enhancement_level=0.8` is the best default, or do you want a different starting point?
4. The docs show `ai_coustics.VAD()` and `VadSettings`, but the quickstart text says VAD support will be added in the future. What is the real current status?
5. Do you want us to demo `local / edge inference` or is the `LiveKit plugin path` sufficient?
6. Are there any event-specific limits on usage, downloads, or model access we should plan around?
7. Do you have a `recommended benchmark or metric` beyond WER that you would love to see teams use?
8. Do you have a preferred `starter repo`, branch, or exact plugin version for this hackathon?

### Important If Time

1. Roughly how large are the model files and how long do they usually take to download on standard Wi-Fi?
2. What are the practical CPU / memory requirements for the recommended model on a normal laptop?
3. Are there known language or accent caveats we should consider for English or German callers?
4. Should we tune for `task completion`, `WER`, or reduction of false insertions from background speakers?
5. Do you have example noisy datasets or recommended public noise samples for a benchmark?
6. If we compare baseline STT vs enhanced STT, is there a recommended STT provider pairing for the cleanest before/after effect?
7. Is there any preferred story between `foreground speaker isolation` and `multi-speaker robustness`?

### Nice To Have

1. What is the one mistake teams usually make when using your SDK?
2. What is the single most impressive metric or demo pattern you would remember?
3. If judges only remember one chart, what should it be?

## 3. Gradium

### Must Ask

1. What is the exact `hackathon access path` for Gradium API keys and credits?
2. For this event, do you want teams to use Gradium for `STT`, `TTS`, or `both`?
3. What is the recommended `LiveKit` integration path for Gradium right now?
4. If we combine `ai-coustics + Gradium`, which component should drive `turn-taking`: Gradium VAD, ai-coustics VAD, or a hybrid?
5. Which Gradium model / voice / language combo would you recommend for a noisy English realtime voice-agent demo?
6. Are there event-specific `rate limits`, latency constraints, or region considerations we should know about?
7. Do you have a starter repo or minimal code sample for a realtime voice agent?
8. For your side challenge, what would make our Gradium usage feel strong rather than generic?

### Important If Time

1. Should we use Gradium websocket streaming directly, or is there a simpler provider adapter path for the event?
2. Are there any audio format gotchas we should watch for when feeding Gradium from LiveKit?
3. Which output format do you recommend for low-latency TTS in our setup?
4. Is there a preferred voice in the library for natural but robust agent demos?
5. Are there any supported-language or accent caveats we should know about?
6. What latency number would you consider a strong live demo?

### Nice To Have

1. What is the most impressive demo pattern you have seen with Gradium at a hackathon?
2. What common mistake makes a Gradium integration feel weak?

## 4. Fastino / Pioneer

### Must Ask

1. What is the fastest valid `fine-tuning path` for the event challenge?
2. What is the realistic `training time` during the event for a small specialized dataset?
3. Do hackathon teams get `credits`, queue priority, or special access?
4. Which use case would you rather see from us:
   - noisy transcript field extraction
   - audio-quality / trust classification
   - synthetic data generation for call transcripts
   - adaptive retraining loop
5. For the challenge, what matters more: `creativity`, `accuracy lift`, `latency`, or `replacement of a general LLM call`?
6. Is there a preferred API mode for the event:
   - Pioneer native `/inference`
   - OpenAI-compatible
   - Anthropic-compatible
7. If we only have time for one extra Pioneer feature beyond the fine-tune, should it be `synthetic data` or `evaluation`?
8. What exact artifact should we cite in the submission: training job ID, dataset name, evaluation ID, model ID, or all of them?

### Important If Time

1. Is there a model you recommend over `gliner2-base-v1` for realtime extraction on CPU?
2. Do you have a recommended schema style for address / vehicle / incident extraction?
3. Are there practical limits on dataset size, training frequency, or concurrent jobs for the event?
4. Can we use public transcripts plus synthetic noise / labels, or do you want a different data story?
5. Is there a simple way to show before/after evaluation in the UI or API without building our own evaluator?
6. Are there any privacy or opt-out settings we need to enable for hackathon data?
7. Is there a simple way to show before/after evaluation in the UI or API without building our own evaluator?

### Nice To Have

1. What would make you say "this clearly deserved the Pioneer prize"?
2. Which part of the platform do most teams ignore but should not?
3. Do you have a public example project closest to our use case?

## 5. Entire

### Must Ask

1. What exactly counts as `using Entire` for the hackathon challenge?
2. Is simply enabling Entire on the repo and producing checkpoints enough, or do you expect the product demo to include Entire visibly?
3. For judging, would a workflow like `AI builds -> checkpoint -> human reviews -> explain session -> ship` qualify cleanly?
4. Do you want us to use the `CLI`, the `web app`, or both?
5. Since we are using `Codex`, what is the exact recommended setup path for the event?
6. Can the checkpoint metadata live in a `separate private repo` during the hackathon if we do not want session logs on the main repo?
7. Are there any privacy or transcript concerns we should think about before enabling Entire on a repo with API keys or secrets?
8. What is the absolute `lowest-effort valid integration` you would accept for judging?

### Important If Time

1. Do you care more about checkpoint capture, explainability, human review, or team collaboration?
2. Would a live use of `entire explain` during judging help our score?
3. Is there a preferred commit cadence so that checkpoints tell a cleaner story?
4. Are there features we should avoid because they are unstable, preview-only, or too slow for a hackathon?
5. Should we use `--checkpoint-remote` to isolate checkpoint data?
6. Do you support the `codex` agent path well enough right now for live event use?

### Nice To Have

1. What is the best hackathon demo pattern you have seen with Entire?
2. What common mistake makes a project look like it "technically used Entire" but did not really show value?

## 6. Aikido

### Must Ask

1. What is the actual `judging rubric` for the security prize?
2. Is a connected repo plus a visible `security report screenshot` sufficient for submission, or do you expect remediation work too?
3. Do you judge on:
   - lowest total issue count
   - lowest severe / critical count
   - percent fixed during event
   - best security posture overall
4. Is a `private GitHub repo` acceptable?
5. Does standard GitHub App scanning count equally to local scanner usage for the challenge?
6. If scans find issues in generated dependencies or starter template code, do you expect us to fix those too?
7. Is there any required format for the screenshot or any required report sections to include?
8. Are there categories you weigh more heavily, such as secrets, SAST, IaC, or dependencies?

### Important If Time

1. Do you recommend any quick wins that have the highest judge impact during a short hackathon?
2. If we use only frontend + Python backend, are there common findings we should preempt?
3. Do you want the scan run before and after fixes as evidence?
4. Are GitHub issues / pull request annotations needed or optional?

### Nice To Have

1. What separates the winning secure build from a normal clean report?
2. Are there known false-positive categories we should interpret carefully?

## 7. Google DeepMind temporary account

### Must Ask

1. Which exact `model families` are enabled on this event project in practice?
2. Are there any effective `quota or spend guardrails` we should avoid hitting during the event?
3. Is there anything we absolutely should not do besides exposing keys publicly?
4. If we use the demo account in local code, is that fully okay, or do you prefer `AI Studio Build` for hackathon projects?
5. Are there any parts of the broader `GCP stack` that are technically available but not intended for hackathon use?
6. Do these event accounts support sharing across teammates, or should one person own the key?

### Important If Time

1. Which model would you recommend if we only use one Gemini model in our project?
2. Are Veo / multimodal features realistically usable in hackathon time, or are they a distraction?
3. Is there an organizer-preferred starter template or code sample?

### Nice To Have

1. What is the coolest realistic use of the temp account for a voice-agent project without derailing the core demo?

## 8. Tavily

### Must Ask

1. Do you want teams to use plain `search/extract`, `crawl/map`, or the `research` API for the event?
2. Is the event refill code enough for normal hackathon use, and are there any hidden limits?
3. If we use Tavily for live retrieval during calls, is that a use case you want to see?
4. Are there preferred best practices for low-latency use inside voice systems?

### Important If Time

1. Which endpoint is the best fit for a voice agent that needs a quick fact lookup without a long research job?
2. Would you prefer we show `search + extract` deterministically instead of a longer `research` flow?
3. Are there any domains / content types where Tavily especially shines for a demo?

### Nice To Have

1. What would make a Tavily usage feel non-generic to you?

## 9. Lovable

### Must Ask

1. Does the event code unlock the exact features we would need for a polished dashboard?
2. Are team collaboration and GitHub sync included in that event access path?
3. If we build a quick control panel in Lovable and sync it to GitHub, is that stable enough for hackathon use?
4. Are there any plan restrictions that would block code editing, project publishing, or GitHub sync?

### Important If Time

1. What is the fastest way to use Lovable as a UI layer on top of an existing backend?
2. Can we safely hand-edit the code after sync without fighting the platform?
3. Is there a recommended pattern for integrating external APIs like our own backend, telli, or Tavily?

### Nice To Have

1. What is the single feature that saves the most time in a 24-hour build?

## 9. Organizer / judging desk

These are not sponsor-specific, but they matter a lot.

### Must Ask

1. Can one project be submitted to the `main track` and multiple `side challenges` at the same time?
2. Is there any limit on how many partner technologies we can claim besides the Aikido note?
3. For each side challenge, do we need:
   - a separate submission
   - separate description text
   - separate evidence attachments
4. Is a `backup video` acceptable if live telephony fails on stage?
5. Are we judged primarily on `live demo`, `repo`, `slides`, or all equally?
6. Is hardware / gift-card prize eligibility tied to in-person presence of all team members?
7. What exact deadline and file/link format do you want?

### Important If Time

1. Are judges likely to walk around before demos, and if so what do they care about most?
2. Are there any common disqualification mistakes in submissions?
