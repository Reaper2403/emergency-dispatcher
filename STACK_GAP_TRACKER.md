# Stack Gap Tracker

Last updated: 2026-04-25

Purpose: live worksheet for unresolved stack questions. Fill this in immediately after talking to a sponsor or organizer.

Current scope:

- core: `Gradbot + ai-coustics + Aikido`
- `telli` is optional
- `Entire` is skipped
- `GLiNER2` and `Tavily` come later

Status legend:

- `Open`
- `Answered`
- `Blocked`
- `Dropped`

Severity legend:

- `P0`: core demo blocker
- `P1`: prize or integration blocker
- `P2`: useful but not critical

## How To Use

1. Before talking to a sponsor, skim their open rows.
2. Ask only the top `P0` and `P1` items first.
3. Write the answer in the `Answer` column.
4. Add where it came from in `Source / Rep`.
5. If the answer changes our plan, update [HACKATHON_PLAN_3HR_INCREMENTS.md](/Users/ashutoshchatterjee/Documents/Hackathon/HACKATHON_PLAN_3HR_INCREMENTS.md).

## telli

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Answered | P0 | Is telli providing the core voice models we need for STT/TTS? | Determines whether telli is core or optional | Assume maybe | `No`. telli is not providing the models we need. | telli rep |
| Open | P0 | Is there a public or sponsor-enabled API for outbound call placement? | Determines whether telephony is in the critical path | Assume `no` until confirmed |  |  |
| Open | P0 | Is there a public or sponsor-enabled API for scheduling calls? | Determines whether we can automate demos instead of using UI / n8n | Assume `unknown` |  |  |
| Open | P0 | Are webhooks available for call status / outcomes / transcripts? | Needed for event-driven updates and cleaner demos | Assume `not guaranteed` |  |  |
| Open | P0 | Can we retrieve transcripts or recordings over API? | Needed for our own metric / replay / backup flows | Assume `unknown` |  |  |
| Open | P1 | What minimum telli usage counts for judging now that telli is not supplying the core models? | Affects whether telli stays in scope at all | Assume contacts + KB may be enough only if rep says yes |  |  |
| Open | P1 | Do teams get test numbers / sandbox access without regulatory setup? | Affects telephony feasibility | Assume sponsor provision is needed |  |  |
| Open | P1 | Are contact property create/update definition endpoints available to us? | Needed for structured CRM updates | Assume listing is documented; creation needs confirmation |  |  |
| Open | P2 | What are rate limits / concurrency limits? | Impacts demo reliability | Assume moderate limits |  |  |

## ai-coustics

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P0 | What is the hackathon access path for SDK keys? | Core integration blocker | Assume sponsor or trial path works |  |  |
| Open | P0 | Which model should we showcase: `QUAIL_VF_L` or `QUAIL_L`? | Affects quality and framing | Assume `QUAIL_VF_L` |  |  |
| Open | P0 | Is `enhancement_level=0.8` the recommended demo setting for our use case? | Affects metric and live demo | Assume `yes` |  |  |
| Open | P0 | What is the real status of VAD support in the LiveKit integration? | Docs are inconsistent | Assume enhancement works; VAD details unclear |  |  |
| Open | P1 | Are there event-specific limits or quotas? | Affects scale / reliability | Assume standard trial unless told otherwise |  |  |
| Open | P1 | What are rough model download size and hardware requirements? | Impacts setup time and fallback planning | Assume manageable but non-trivial |  |  |
| Open | P2 | Do they want local/edge emphasis or LiveKit plugin is enough? | Affects pitch framing | Assume plugin is enough |  |  |

## Gradium

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P0 | What is the hackathon access path for `Gradium` API keys / credits? | Core voice-model blocker | Assume sponsor onboarding is required |  |  |
| Open | P0 | Should we use Gradium for `STT`, `TTS`, or `both` in the main demo? | Defines the core voice path | Assume likely `both` |  |  |
| Open | P0 | What is the recommended `LiveKit` integration path for Gradium at the event? | Affects implementation speed | Assume websocket integration or provider adapter |  |  |
| Open | P1 | Which model / voice / language configuration should we start with? | Affects demo quality | Assume default model + English voice |  |  |
| Open | P1 | Should turn-taking be driven by `Gradium VAD`, `ai-coustics VAD`, or our own hybrid logic? | Affects latency and trust scoring | Assume hybrid until advised otherwise |  |  |
| Open | P1 | Are there event-specific rate limits, regions, or latency constraints? | Affects reliability | Assume standard limits |  |  |
| Open | P2 | What does Gradium most want to see to count as strong challenge usage? | Helps if we chase their side prize too | Assume core STT/TTS usage may count |  |  |

## LiveKit

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P1 | Do we have enough free-tier or event quota for the full demo? | Could affect deployment / debugging | Assume yes for small demo |  |  |
| Open | P2 | Is browser demo enough if telephony is not ready? | Affects fallback confidence | Assume yes |  |  |

## Fastino / Pioneer

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Answered | P0 | Does off-the-shelf `gliner2-base-v1` count for the prize? | Determines whether side prize is realistic | Assume `not guaranteed` | `No`. Sponsor says the challenge expects a specialized fine-tune rather than just off-the-shelf GLiNER usage. | Fastino rep |
| Answered | P0 | If not, what is the minimum qualifying Pioneer usage? | Determines work scope | Assume training or eval may be needed | Fine-tune for a specialized task. Sponsor framing: GLiNER is multitask, and the goal is to specialize it so it can approach or beat GPT-4o on a narrow task. | Fastino rep |
| Open | P1 | How long do training jobs take during the event? | Affects whether we launch one early | Assume several hours |  |  |
| Open | P1 | Are hackathon credits / priority access provided? | Affects feasibility | Assume `unknown` |  |  |
| Open | P1 | Which use case would the rep most want to see? | Affects novelty layer | Assume noisy transcript extraction is best |  |  |
| Open | P2 | Which API mode should we use: native or OpenAI-compatible? | Impacts implementation convenience | Assume native or direct model load is fine |  |  |

## Entire

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P0 | What exactly counts as a qualifying Entire integration? | Determines whether we chase the prize at all | Assume docs alone are insufficient |  |  |
| Open | P1 | Is simply enabling Entire on the repo enough? | Determines minimum effort path | Assume `no` until confirmed |  |  |
| Open | P1 | Is using `Codex` officially supported enough for the event? | Affects friction and risk | Assume CLI supports it, challenge setup unknown |  |  |
| Open | P1 | Can / should checkpoint metadata be stored in a separate private repo? | Affects privacy and setup | Assume yes via `--checkpoint-remote` |  |  |
| Open | P2 | Do they want `entire explain` visibly used in the demo? | Affects pitch design | Assume optional |  |  |

## Aikido

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P1 | What is the judging rubric for "Most Secure Build"? | Determines what we optimize for | Assume clean report + story matters |  |  |
| Open | P1 | Is screenshot evidence alone enough for submission? | Affects effort | Assume enough to submit, not enough to assume win |  |  |
| Open | P1 | Does GitHub App scan count the same as local scan? | Affects setup choice | Assume yes unless stated otherwise |  |  |
| Open | P2 | Do they care most about severe issues, total issues, or fixes made during the event? | Affects prioritization | Assume severe issues matter most |  |  |

## Google DeepMind temporary account

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Answered | P2 | Which exact models / products are enabled for the event? | Determines if Google is useful at all | Assume Gemini API + AI Studio access | Demo account comes through Cloud Console with a project already created. AI Studio deployment, Agent platform, Model Garden, and broader GCP stack access are available. | Google DeepMind rep |
| Answered | P2 | Are there practical quota / spend guardrails? | Avoids accidental project shutdown | Assume yes, but undocumented | Billing is already set up on the demo project. Still treat it as event-scoped access and keep keys out of public repos. | Google DeepMind rep + official temp-account guide |
| Answered | P2 | Is Vertex AI intended, or only AI Studio? | Affects coding path | Assume AI Studio keys are the path | Not AI Studio only. Access is through GCP/Cloud Console with broader platform access. | Google DeepMind rep |

## Tavily

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P2 | Is the event refill code enough for our likely usage? | Determines whether we can rely on it | Assume yes for light use |  |  |
| Open | P2 | Which endpoint do they most want teams to show? | Helps if we choose to use it | Assume `search + extract` is safest |  |  |

## Lovable

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P2 | Does the event code unlock the features we need for a dashboard? | Determines whether it saves time | Assume maybe, not verified |  |  |
| Open | P2 | Is GitHub sync included with the event plan? | Determines handoff into our normal repo | Assume unknown |  |  |

## Organizer / judging desk

| Status | Severity | Gap | Why it matters | Current assumption | Answer | Source / Rep |
| --- | --- | --- | --- | --- | --- | --- |
| Open | P0 | Can one project enter the main track and multiple side challenges? | Core prize-stack assumption | Assume yes, but must confirm |  |  |
| Open | P0 | Are multiple partner technologies allowed in one submission? | Affects stack choice | Assume yes except Aikido note |  |  |
| Open | P1 | Is a backup video acceptable if live telephony fails? | Reduces demo risk | Assume yes |  |  |
| Open | P1 | What exact evidence format is expected for side challenges? | Avoids submission mistakes | Assume screenshots + description |  |  |
