# Stack Internal Reference

Last updated: 2026-04-25

Scope: internal reference for the current build stack and prize-stack partners.

Current build scope:

- use `Gradbot` first
- use `ai-coustics` for input denoising
- use `Aikido` for the security side challenge
- defer `GLiNER2`, `Tavily`, and most `telli` work until the first demo is stable

Method:

- only official docs or official pages were used
- anything not explicitly documented is marked as unknown or assumption
- this document is meant to be read quickly during implementation

Confidence legend:

- `Verified`: directly stated in official docs
- `Likely`: strongly implied by official docs, but not stated as an integration contract
- `Unknown`: not verified publicly and must be asked

## Quick Matrix

| Sponsor / Tool | Role in stack | Verified public surface | Main unknowns | Default stance |
| --- | --- | --- | --- | --- |
| `telli` | optional telephony / CRM / KB layer | contacts API, contact properties, KB, some phone-number APIs, n8n | programmatic call placement, webhooks, transcripts API, hackathon sandbox, judging value without core models | use only if telephony / contact / KB integration is worth the effort |
| `ai-coustics` | realtime audio enhancement | LiveKit plugin, SDK docs, file API | hackathon key path, model choice for demo, exact LiveKit/VAD behavior | use LiveKit plugin with `QUAIL_VF_L` at `0.8` |
| `Gradium` | candidate core STT/TTS model layer | realtime STT/TTS docs, WebSocket API, voice library, VAD, credits API | hackathon key path, best event config, LiveKit integration guidance, challenge expectations | likely core STT/TTS path if access is smooth |
| `LiveKit` | realtime voice runtime | agent framework, cloud deploy, telephony support | event-specific quotas / easiest deployment path | use browser demo as fallback |
| `Pioneer / Fastino` | specialized extraction / classification / prize angle | inference, datasets, synthetic data, training, evals, GLiNER2 models | training timing, credits, preferred demo, minimum qualifying artifact | use base GLiNER2 only for prototyping; fine-tune if chasing prize |
| `Entire` | human collaboration / audit / prize angle | CLI, checkpoints, sessions, GitHub sync | what counts as a qualifying hackathon integration | do not assume our custom dashboard alone counts |
| `Aikido` | security prize | GitHub App scan, local scanner, code scanning | exact judging bar, screenshot sufficiency | connect repo early and capture report |
| `Tavily` | optional live retrieval | Search / Extract / Crawl / Map / Research APIs, CLI | event-specific extra credits, preferred use case | keep optional |
| `Lovable` | optional UI acceleration | GitHub sync, code editor, build-with-URL API | whether event code covers our intended usage | use only if it saves time |
| `Google DeepMind temp account` | optional Gemini / GCP / model access | temp-account guide plus sponsor-confirmed Cloud Console demo account | exact model families enabled in practice, spend guardrails, discouraged services | treat as disposable event project with strict key hygiene |

## 1. telli

### Why we care

- contact and customer context
- voice-agent prompt/runtime conventions
- knowledge base
- possible call handling / phone number / outcome automation

### Verified from official docs

- Base API host is `https://api.telli.com`
- API key comes from `Settings > API & Webhooks`
- Auth uses `Authorization: Bearer <api-key>`
- V2 API is public for contacts and contact properties
- V1 API remains operational for some legacy endpoints
- Knowledge Base supports `PDF`, `DOCX`, `TXT`, and `MD`
- KB limits:
  - up to `5` files per KB
  - up to `20 MB` per file
  - about `1,500` pages total
  - `1` KB per agent
- KB search is real-time during calls and uses semantic + keyword search
- Prompt docs explicitly recommend silent transcript correction and short, clear spoken responses
- Phone-number replacement is documented at `POST /v1/phone-numbers/{id}/replace`
- Batch contact creation is documented at `POST /v1/add-contacts-batch`
- n8n docs say the verified telli node supports:
  - adding contacts
  - scheduling calls
  - updating CRM status based on call outcomes

### Verified endpoints / surfaces

V2 contacts:

- `POST /v2/contacts`
- `GET /v2/contacts/{id}`
- `GET /v2/external/contacts/{externalId}`
- `PATCH /v2/contacts/{id}`
- `DELETE /v2/contacts/{id}`
- `GET /v2/contacts`
- `GET /v2/properties/contacts`

V1 still documented:

- `POST /v1/add-contact`
- `POST /v1/add-contacts-batch`
- `GET /v1/get-contact/:contactId`
- `GET /v1/get-contact-by-external-id/:externalId`
- `PATCH /v1/update-contact`
- `DELETE /v1/delete-contact/:contact_id`
- `POST /v1/phone-numbers/{id}/replace`

### Verified product/runtime notes

- Agent persona settings include language, voice, speed, background noise, and first messages
- Prompt cookbook emphasizes:
  - infer intended meaning even when STT is imperfect
  - keep answers short
  - speak naturally
- Customer context can be passed as contact details and referenced in prompts
- KB can be explicitly nudged with `[searchKnowledgeBase]`

### Unknown / unverified

- whether there is a documented public endpoint for programmatic outbound call initiation
- whether there is a documented public endpoint for scheduling a call directly through REST
- whether there is a public webhook API for call outcomes, transcripts, or recordings
- whether there is a public API for transcripts / recordings retrieval
- whether hackathon teams get test phone numbers without full regulatory verification
- rate limits, concurrency limits, and sandbox constraints
- whether telli can bridge directly into a LiveKit flow or whether they expect us to use telli more loosely
- whether contact property creation / mutation endpoints beyond listing are exposed and enabled for us

### Sponsor-confirmed event guidance

- telli is `not` providing the core voice models we need for this project
- treat telli as an optional layer for:
  - telephony
  - contacts
  - knowledge base
  - CRM / workflow context
- do not plan around telli as the `STT/TTS` provider

### Default assumption

Use telli for, at most:

- contacts
- contact properties
- knowledge base
- prompt/runtime conventions
- optional telephony / workflow integration

Do not assume:

- core STT / TTS models
- direct programmatic call scheduling
- direct programmatic outbound call placement
- public webhooks / transcript export

### Sources

- [Migration Guide](https://docs.telli.com/v2-migration-guide)
- [Knowledge Base](https://docs.telli.com/cookbooks/knowledgebase/overview)
- [n8n Integration](https://docs.telli.com/integrations/n8n)
- [Add Customer Context](https://docs.telli.com/en/get-started/add-customer-context)
- [Agent Persona](https://docs.telli.com/en/get-started/agent-persona)
- [Global Rules & Behavior](https://docs.telli.com/cookbooks/how-to-prompt/prompt-structure/global-rules-behavior)
- [Add Contacts Batch](https://docs.telli.com/api-reference/add-contacts-batch)
- [Replace Phone Number](https://docs.telli.com/api-reference/replace-phone-number)
- [Phone Numbers](https://docs.telli.com/de/platform/phone-numbers)
- [Live Monitoring](https://docs.telli.com/de/platform/live-monitoring)

## 2. ai-coustics

### Why we care

- core differentiator for the main track
- realtime enhancement before STT / agent logic
- measurable WER / task-completion gains under noise

### Verified from official docs

- Real-Time SDK runs locally or on edge infrastructure
- The LiveKit plugin is the official quickstart path
- `uv add livekit-plugins-ai-coustics` is the documented package path
- Real-Time SDK free trial is `30 days`
- File Processing API free allowance is `120` processing minutes
- The recommended model for single near-field speaker isolation is `Quail Voice Focus`
- For voice-agent use cases, `enhancement_level=0.8` is the documented best starting point on challenging data
- `0.5` is conservative and preserves ambiguous speech more often
- `1.0` is aggressive and may suppress quiet foreground speech
- Quail models are optimized for STT / Voice AI, not necessarily for best human listening quality
- Rook models are for human listening quality rather than STT-first use cases
- File API base host is `https://api.ai-coustics.io/v2`
- File API auth is `X-API-Key`
- File API endpoints:
  - `POST /v2/medias`
  - `GET /v2/medias/{media_uid}/metadata`
  - `GET /v2/medias/{media_uid}/file`
- File API rate limits:
  - upload `10/min`
  - metadata `120/min`
  - file download `60/min`
- Model files are now separate downloads rather than bundled in the SDK

### Verified LiveKit integration notes

- Quickstart uses:
  - `ai_coustics.VAD()`
  - `ai_coustics.audio_enhancement(...)`
- The quickstart page documents `VadSettings` in code examples

### Doc inconsistency to note

The same LiveKit quickstart page also says:

- "Support for Voice Activity Detection will be added in the future"

This conflicts with the code sample showing `ai_coustics.VAD()` and `VadSettings`.

Interpretation:

- the docs are inconsistent
- do not assume we understand the exact supported VAD behavior until sponsor confirms

### Unknown / unverified

- whether hackathon teams get SDK keys directly or must use the normal trial flow
- whether the sponsor wants `QUAIL_VF_L` or `QUAIL_L` showcased
- whether the event wants local/edge processing or just the LiveKit plugin demo
- exact CPU / memory profile we should plan for on our laptop
- size and download time of the required model files on event Wi-Fi
- exact supported language coverage and any caveats for accented / noisy German or English speech
- whether there are event-specific quota limits beyond the standard trial
- exact meaning of the VAD support inconsistency in the docs

### Default assumption

Start with:

- LiveKit plugin
- `Quail Voice Focus`
- `enhancement_level=0.8`
- browser / playground demo path

Do not block on:

- file API
- custom runtime tuning
- perfect understanding of VAD internals

### Sources

- [Getting Started](https://docs.ai-coustics.com/)
- [LiveKit Quickstart](https://docs.ai-coustics.com/tutorials/livekit-quickstart)
- [Speech Enhancement for Voice AI Systems](https://docs.ai-coustics.com/guides/speech-enhancement-for-asr)
- [Models](https://docs.ai-coustics.com/guides/models)
- [Pricing & Billing](https://docs.ai-coustics.com/guides/pricing)
- [Model Naming Changes](https://docs.ai-coustics.com/guides/migrations/model-naming)
- [Rate Limiting](https://docs.ai-coustics.com/api-reference/rate-limiting)
- [Upload Media](https://docs.ai-coustics.com/api-reference/v2/upload-media-file)
- [Retrieve Metadata](https://docs.ai-coustics.com/api-reference/v2/retrieve-media-metadata)
- [Download File](https://docs.ai-coustics.com/api-reference/v2/download-media-file)
- [Performance](https://docs.ai-coustics.com/knowledge/performance)
- [Changelog](https://docs.ai-coustics.com/sdk/changelog)

## 3. Gradium

### Why we care

- likely core `STT/TTS` layer now that telli is not supplying the voice models we need
- possible side prize
- documented realtime websocket contracts we can wire into LiveKit or our own runtime

### Verified from official docs

- Gradium provides realtime `Text-to-Speech` and `Speech-to-Text`
- API auth uses `x-api-key`
- REST base URL is `https://api.gradium.ai/api`
- WebSocket base URL is `wss://api.gradium.ai/api`
- STT websocket endpoint is `wss://api.gradium.ai/api/speech/asr`
- TTS websocket endpoint is `wss://api.gradium.ai/api/speech/tts`
- STT supports realtime streaming and `VAD`
- TTS supports low-latency streaming audio
- STT setup message includes:
  - `type: "setup"`
  - `model_name`
  - `input_format`
- STT ready response includes:
  - `sample_rate` typically `24000`
  - `frame_size` typically `1920`
- Recommended PCM input for STT is:
  - `24kHz`
  - `16-bit signed little-endian`
  - `mono`
  - `1920` samples per frame
- STT streams:
  - `text`
  - `step` VAD messages
  - `end_text`
  - `flushed`
  - `end_of_stream`
- STT VAD docs recommend looking at the `2s` horizon and triggering end-of-turn when `inactivity_prob > 0.5`
- TTS setup includes:
  - `type: "setup"`
  - `voice_id`
  - `model_name`
  - `output_format`
- TTS supports output formats including:
  - `wav`
  - `pcm`
  - `opus`
- Voice library has `237` voices across:
  - English
  - French
  - German
  - Spanish
  - Portuguese
- Custom voice cloning is supported
- Credits endpoint is documented

### Verified hackathon-relevant fit

Gradium can cleanly cover:

- realtime `STT`
- realtime `TTS`
- VAD / turn-taking signals
- voice selection for a polished demo

### Verified Gradbot notes

- `Gradbot` is presented by Gradium as an `open source voice agent framework`
- the official Gradbot page says it can get to a first agent in about `50 lines`
- it handles:
  - `STT`
  - `LLM`
  - `TTS`
  - `VAD`
  - turn-taking
  - fillers
  - interruptions
  - tool calls
- it supports `any OpenAI-compatible LLM`
- official install command is `pip install gradbot`
- Gradium positions `Gradbot` as the fast `prototyping` path
- the same page says for `production`, use Gradium APIs with mature integrations like `LiveKit` and `Pipecat`

### Unknown / unverified

- hackathon API key / credit path
- whether the hackathon team should start from `Gradbot` or raw Gradium APIs
- whether Gradium should power `STT`, `TTS`, or both for the event
- best integration path with `LiveKit` for hackathon speed
- recommended voice / model / language combination for our demo
- event-specific rate limits, quotas, or region guidance
- whether the sponsor wants us to use Gradium's own VAD or only STT/TTS

### Default assumption

Use `Gradbot` first, with Gradium as the voice-model backend.

Treat these as separate concerns:

- `ai-coustics` = audio enhancement
- `Gradbot/Gradium` = speech recognition + speech synthesis + voice loop
- `LiveKit` = optional runtime fallback or later production-style path

### Sources

- [Gradbot](https://gradium.ai/gradbot)
- [Documentation Home](https://docs.gradium.ai/)
- [API Reference](https://docs.gradium.ai/api-reference/introduction)
- [STT WebSocket](https://docs.gradium.ai/api-reference/endpoint/stt-websocket)
- [Voices Overview](https://docs.gradium.ai/guides/voices/overview)
- [Public API Docs](https://gradium.ai/api_docs.html)

## 4. LiveKit

### Why we care

- easiest public path to a working realtime voice agent
- official plugin path for ai-coustics
- browser demo fallback if telephony is delayed

### Verified from official docs

- LiveKit Agents is a realtime framework for voice, video, and physical AI agents
- Works with Python and Node.js
- Agent starter templates exist
- Cloud deploy flow is:
  - `lk cloud auth`
  - `lk agent create`
- A browser-based Agent Console exists for debugging
- LiveKit supports telephony integration
- LiveKit Cloud includes observability and logs

### Unknown / unverified

- event-specific cloud quotas and concurrency
- whether there is any hackathon sponsor support or credits beyond free tier
- whether we should self-host or stay cloud-only for the event

### Default assumption

Use LiveKit Cloud plus browser demo first. Telephony is optional, not the critical path.

### Sources

- [Agents Introduction](https://docs.livekit.io/agents/)
- [Agent Deployment Quickstart](https://docs.livekit.io/deploy/agents/quickstart/)
- [LiveKit GitHub Org](https://github.com/livekit)
- [Agent Starter Python](https://github.com/livekit-examples/agent-starter-python)

## 5. Fastino / Pioneer / GLiNER2

### Why we care

- strongest technical novelty layer
- can replace a generic LLM extraction / classification step
- possible side prize

### Verified from official docs

- Base API host is `https://api.pioneer.ai`
- Auth uses `X-API-Key`
- Bearer auth is also supported
- OpenAI-compatible path exists at `https://api.pioneer.ai/v1`
- Anthropic-compatible path exists at `https://api.pioneer.ai`
- Native inference endpoint is `POST /inference`
- Base model catalog endpoint is `GET /base-models`
- Supported task types:
  - `extract_entities`
  - `classify_text`
  - `extract_json`
  - `generate`
- Inference history / feedback endpoints exist
- Dataset endpoints exist under `/felix/datasets`
- Synthetic data generation exists via:
  - `POST /generate`
  - `GET /generate/jobs/:job_id`
- Training endpoints exist under `/felix/training-jobs`
- Evaluation endpoints exist under `/felix/evaluations`
- Project / deployment endpoints exist under `/projects`
- Available encoder models include:
  - `fastino/gliner2-base-v1`
  - `fastino/gliner2-large-v1`
  - `fastino/gliner2-multi-v1`
  - `fastino/gliner2-multi-large-v1`
- Dataset upload supports `JSON`, `JSONL`, `CSV` up to `50 MB`
- FAQ says:
  - no storage charge
  - free tier exists for experimenting
  - Pro is for uncapped inference
  - they do train on user data by default, with opt-out on Pro and Custom

### Verified hackathon-relevant fit

Pioneer can cleanly power:

- field extraction from noisy transcripts
- audio-quality or incident-type classification
- schema-driven extraction without a general LLM

### Unknown / unverified

- how long training jobs currently take on event infrastructure
- whether event teams get credits or special queue priority
- which exact use case they want to reward: synthetic data, eval, adaptive inference, GLiNER2, or full fine-tune
- whether they want inference via native Pioneer API or openai-compatible mode

### Sponsor-confirmed event guidance

- Off-the-shelf `fastino/gliner2-base-v1` alone is not the intended challenge path
- The sponsor expects a `specialized fine-tune`
- Sponsor framing: `GLiNER` is a multitask base, and teams should specialize it so it can approach or beat `GPT-4o` on a narrow task

### Remaining unknown / unverified

- how long training jobs currently take on event infrastructure
- whether event teams get credits or special queue priority
- which exact use case they most want to reward: synthetic data, eval, adaptive inference, extraction, classification, or a full fine-tune
- whether they want inference via native Pioneer API or openai-compatible mode
- what exact artifact they expect in the submission beyond "we fine-tuned it"

### Default assumption

Technically, use off-the-shelf GLiNER2 first only as a prototype aid.

For prize strategy, assume:

- off-the-shelf use does not satisfy the intended prize bar
- a fine-tune is required if we want the Pioneer side-prize story to be credible
- if we cannot start fine-tuning early, Pioneer should stay optional and must not block the main demo

### Sources

- [Pioneer Docs](https://agent.pioneer.ai/docs)
- [Pioneer llms.txt](https://agent.pioneer.ai/llms.txt)
- [Pioneer llms-full.txt](https://agent.pioneer.ai/llms-full.txt)
- [Pioneer Home](https://pioneer.ai/)
- [Fastino Home](https://fastino.ai/)
- [Fastino GLiNER Page](https://fastino.ai/gliner)

## 6. Entire

### Why we care

- possible side prize for developer / human-agent collaboration
- can give us a credible audit / review / takeover story if challenge criteria allow it

### Verified from official docs

- Entire is a developer platform that captures AI coding sessions into Git-linked checkpoints
- Install via Homebrew or install script
- Enable in repo with `entire enable`
- CLI supports agent integration flags including `--agent codex`
- Entire stores permanent checkpoint metadata on branch `entire/checkpoints/v1`
- Checkpoints are linked to commits with `Entire-Checkpoint: <id>` trailer
- Entire captures:
  - conversation transcript
  - code changes
  - token usage
  - metadata
  - line attribution
- Entire has web UI for checkpoints and sessions
- `entire explain` can generate or show explanations for sessions / commits
- Session data is stored locally and on the checkpoint branch
- Entire attempts to anonymize sensitive data such as API tokens in transcripts
- A separate checkpoint remote can be configured with `--checkpoint-remote`

### Important limitation

The public docs describe Entire as a coding-session / checkpoint platform, not a general-purpose ops dashboard.

That means:

- our custom escalation dashboard is not automatically an Entire integration
- challenge qualification is sponsor-defined, not docs-defined

### Unknown / unverified

- what minimum integration counts for the hackathon challenge
- whether simply enabling Entire on the repo qualifies
- whether they expect actual use of checkpoints / explain / session history during the demo
- whether a separate private checkpoint repo is encouraged for hackathon use
- whether they support or recommend the `codex` integration path during the event

### Default assumption

Use Entire only if the sponsor confirms a clear low-effort qualification path.

Do not build our core demo around Entire.

### Sources

- [Introduction](https://docs.entire.io/introduction)
- [Quickstart](https://docs.entire.io/quickstart)
- [Installation](https://docs.entire.io/cli/installation)
- [Commands](https://docs.entire.io/cli/commands)
- [Configuration](https://docs.entire.io/cli/configuration)
- [Core Concepts](https://docs.entire.io/core-concepts)
- [Web Overview](https://docs.entire.io/web/overview)
- [Checkpoints](https://docs.entire.io/web/checkpoints)
- [Repositories](https://docs.entire.io/web/repositories)

## 7. Aikido

### Why we care

- easiest extra prize shot
- low engineering overhead

### Verified from official docs

- GitHub App connection is read-only
- After connection, scans start automatically
- First results usually appear in about a minute
- Aikido code scanning covers:
  - dependencies
  - SAST
  - IaC
  - secrets
  - malware
  - more
- Local scanner exists if needed
- Local scanner requirements for Linux / CI docs indicate roughly:
  - `2-4` CPU cores
  - `8-16 GB` RAM
  - outbound HTTPS
- Local scanning support inside existing SCM-integrated workspaces is not enabled by default and may require Pro + activation

### Unknown / unverified

- exact judging rubric for the hackathon security prize
- whether a single screenshot is enough or whether they want issue remediation narrative too
- whether a private personal repo is acceptable
- whether local scanner counts the same as cloud/GitHub App scan for the challenge
- whether they care about absolute issue count, severity mix, or percentage fixed during the hackathon

### Default assumption

Connect the repo with the GitHub App and capture the report. Use local scanning only if GitHub integration fails.

### Sources

- [Connect GitHub Organization](https://help.aikido.dev/code-scanning/connect-your-source-code/connect-github-account-to-aikido)
- [Code Scanning Overview](https://help.aikido.dev/code-scanning/code-scanning-overview)
- [Local Code Scanning](https://help.aikido.dev/code-scanning/local-code-scanning)
- [CLI Options for Local Scanner](https://help.aikido.dev/code-scanning/local-code-scanning/cli-options-for-local-scanner)
- [Local Scanning in Existing SCM Workspaces](https://help.aikido.dev/code-scanning/local-code-scanning/local-scanning-in-existing-scm-integrated-workspaces)

## 8. Google DeepMind temporary account

### Why we care

- optional access to higher Gemini quota and paid models
- possible fallback for reasoning, summarization, or multimodal experimentation

### Verified from the official temporary-account guide

- temp accounts are specifically for hackathons sponsored by Google DeepMind or Google Cloud
- account/project will be deleted very soon after the hackathon
- API keys must not be pushed publicly to GitHub
- abusive usage can cause disqualification / account shutdown
- flow is:
  - log into the provided account
  - import the provided project in AI Studio
  - create or retrieve an API key
- the imported project key should be Tier 3
- paid models are available with the temporary account, including examples like:
  - `Gemini 3.1 Pro`
  - `Veo`
  - `Nano-Banana Pro/2`
- Cloud Run use is mentioned, but resources are temporary

### Sponsor-confirmed event guidance

- We will receive `Cloud Console` demo-account credentials
- The demo `project is already created`
- `billing is already set up`
- We should get an `API key`
- `AI Studio` can directly deploy applications
- `Agent platform` is available
- `Model Garden` is available
- broader `GCP stack access` is available on the demo project

### Unknown / unverified

- which exact model families are enabled in practice on the event project
- whether there are spend / request caps beyond the warning in the guide
- whether there are any restrictions on using the temp account from local code vs AI Studio Build
- whether any parts of the broader GCP stack are technically available but discouraged for hackathon scope

### Default assumption

Treat Google access as optional and disposable. It is broader than AI Studio only, but it still should not become a core dependency of the main demo.

### Source

- `goo.gle/hackathon-account` official guide fetched on 2026-04-25

## 9. Tavily

### Why we care

- optional real-time retrieval if we want live knowledge during calls

### Verified from official docs

- Base API host is `https://api.tavily.com`
- Auth uses `Authorization: Bearer tvly-...`
- Endpoints:
  - `/search`
  - `/extract`
  - `/crawl`
  - `/map`
  - `/research`
- Optional `X-Project-ID` header exists for usage tracking
- Free plan includes `1,000` credits per month
- Documented rate limits:
  - development key `100 RPM`
  - production key `1,000 RPM`
  - crawl `100 RPM`
  - research creation `20 RPM`
- CLI exists via `tvly`
- Research API supports polling and streaming

### Unknown / unverified

- whether the event refill code has any special limits or expiry beyond the note on the hackathon page
- whether the sponsor wants a specific use case highlighted
- whether using Tavily meaningfully helps any judging category we care about

### Default assumption

Keep Tavily optional. Only use it if we have a clean, high-signal retrieval feature.

### Sources

- [Welcome](https://docs.tavily.com/welcome)
- [API Introduction](https://docs.tavily.com/documentation/api-reference/introduction)
- [Rate Limits](https://docs.tavily.com/documentation/rate-limits)
- [Credits & Pricing](https://docs.tavily.com/documentation/api-credits)
- [Crawl Endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/crawl)
- [Research Endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/research)
- [Research Status](https://docs.tavily.com/documentation/api-reference/endpoint/research-get)
- [Tavily CLI](https://docs.tavily.com/documentation/tavily-cli)

## 10. Lovable

### Why we care

- optional shortcut for a polished dashboard

### Verified from official docs

- Lovable is a full-stack AI development platform
- Code can be synced to GitHub
- GitHub sync is two-way on the default branch
- Each project can be linked to one repository
- Code editor is available on paid plans
- Published apps can be deployed to a Lovable URL
- Lovable API currently focuses on "Build with URL"

### Unknown / unverified

- whether the event code covers the exact features we would use
- whether team collaboration features are available with the event plan
- whether there are any limits that would make it slower than just building the dashboard ourselves

### Default assumption

Use Lovable only if we need UI speed and the code redemption works immediately.

### Sources

- [Welcome](https://docs.lovable.dev/)
- [Connect project to GitHub](https://docs.lovable.dev/integrations/github)
- [Lovable API](https://docs.lovable.dev/integrations/lovable-api)
- [Code Mode](https://docs.lovable.dev/features/code-mode)
- [FAQ](https://docs.lovable.dev/introduction/faq)
- [Publish](https://docs.lovable.dev/features/publish)
- [Self-hosting](https://docs.lovable.dev/tips-tricks/self-hosting)

## Recommended Default Build Path

If no sponsor answers arrive yet, the safest implementation path is:

1. `Gradbot + ai-coustics` demo
2. custom extraction / trust logic in our own code
3. use `telli` only if contacts / KB / telephony add clear value
4. connect `Aikido` to the repo
5. keep `Entire`, `Pioneer`, `Tavily`, and `Lovable` optional until sponsor constraints are resolved; only chase `Pioneer` if we can start a fine-tune early

## Biggest Remaining Knowledge Gaps

1. `Gradbot` event access and fastest valid setup path
2. `ai-coustics` event access details and VAD ambiguity
3. `telli` residual value as optional telephony / CRM / KB layer
4. `Pioneer` training timing and qualifying artifact
5. `Entire` prize qualification bar
6. `Aikido` judging criteria beyond "have a report"
