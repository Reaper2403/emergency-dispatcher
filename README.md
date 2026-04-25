# Emergency Dispatcher

Hackathon repo for a real-time emergency dispatch voice agent designed to work in noisy, real-world conditions.

## Current Scope

- `Gradbot` for the core voice agent loop
- `ai-coustics` for input audio enhancement
- `Gradium` for voice model infrastructure
- `Aikido` for security scanning
- optional `Google` model path via ADC

## Near-Term Goal

Build a lean demo that can:

- hear reliably under noise
- assign dispatch priority
- validate or normalize an address
- create a structured incident ticket

## Dev Docs

- [NEXT_3_HOURS.md](./NEXT_3_HOURS.md)
- [STACK_DOCS_INDEX.md](./STACK_DOCS_INDEX.md)
- [STACK_INTERNAL_REFERENCE.md](./STACK_INTERNAL_REFERENCE.md)
- [STACK_GAP_TRACKER.md](./STACK_GAP_TRACKER.md)
- [SPONSOR_QUESTION_BANK.md](./SPONSOR_QUESTION_BANK.md)

## Local Setup

1. Use Python `3.13`
2. Copy `.env.example` to `.env`
3. Fill in the required provider keys
4. For Google, authenticate with ADC instead of an API key
