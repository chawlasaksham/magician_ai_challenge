# Vera Elite — magicpin AI Challenge Submission

**Vera** is an intelligent, context-grounded AI merchant assistant built for local businesses across 5 distinct categories: Dentists, Salons, Restaurants, Gyms, and Pharmacies.

---

## 1. Architecture Overview

```
                      ┌──────────────────────────────────────┐
                      │        magicpin Judge Harness        │
                      └──────────────────┬───────────────────┘
                                         │ HTTP
                                         ▼
                               ┌───────────────────┐
                               │  bot.py (FastAPI) │
                               └─────────┬─────────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
                 ▼                       ▼                       ▼
        ┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
        │  ContextStore   │    │    Composer       │    │  Conversation   │
        │ (Thread-Safe,   │    │  (Deterministic + │    │     Manager     │
        │  Atomic Ver.)   │    │    LLM Fallback)  │    │  (Anti-Repeat,  │
        └─────────────────┘    └─────────┬─────────┘    │   Auto-Reply)   │
                                         │              └─────────────────┘
                                         ▼
                               ┌───────────────────┐
                               │  Guardrails &     │
                               │  Taboo Filtering  │
                               └───────────────────┘
```

The service exposes the five required endpoints specified in `challenge-testing-brief.md`:
1. `GET /v1/healthz` — Liveness & uptime probe returning loaded context counts.
2. `GET /v1/metadata` — Team metadata, model info, and version.
3. `POST /v1/context` — Atomic, versioned ingestion of Category, Merchant, Customer, and Trigger contexts with idempotency.
4. `POST /v1/tick` — Periodic wake-up for proactive outbound composition grounded on 4-context resolution.
5. `POST /v1/reply` — Synchronous multi-turn inbound handling with semantic intent detection, auto-reply classification, and hostility handling.
*(Optional `POST /v1/teardown` is also exposed for state resetting between test suites).*

---

## 2. Core Capabilities

### A. Dynamic 4-Context Grounding & High Specificity
- **No Seed Hardcoding**: The bot works dynamically with arbitrary and injected contexts.
- **Verifiable Metric Anchoring**: Every generated message draws directly from concrete numbers in the payload (exact prices in ₹, percentages %, review counts, batch numbers, clinical trial participants, dates, and distances).
- **Zero Hallucination Guarantee**: Facts are extracted strictly from the 4 contexts provided to the bot.

### B. Category-Voiced Merchant Personalization
- **Dentists**: Clinical, peer-to-peer, technical accuracy, using `Dr.` honorific.
- **Salons**: Warm, friendly, beauty-centric, consultation and prep timing.
- **Restaurants**: Operator-to-operator, delivery cover shifts, packaging tiers.
- **Gyms**: Motivational, coaching tone, seasonal resolution cycles.
- **Pharmacies**: Precise, trustworthy, CDSCO regulatory adherence, chronic refill tracking.

### C. WhatsApp Business Auto-Reply & Loop Detection
- Pattern matching on common auto-reply phrases (`"thank you for contacting"`, `"away from desk"`, `"automated response"`).
- Consecutive auto-reply threshold: switches to `end` immediately on loop detection.

### D. Intent Transition & Action Mode
- Immediately transitions into action mode upon merchant commitment (`"ok let's do it"`, `"sounds good"`, `"yes"`).
- Emits action verbs (`done`, `draft`, `confirm`, `sending`) and strictly forbids qualifying questions (`"would you"`, `"do you"`, `"can you"`).

### E. Safety & Guardrails
- **Taboo Vocabulary**: Replaces forbidden words (`cure`, `guaranteed`, `100% safe`, `miracle`) with compliant medical/business phrasing.
- **Anti-Repetition**: SHA-256 fingerprinting across past sent messages in the conversation prevents duplicate outbound messages.
- **Single CTA Rule**: Every proactive message ends with exactly one clear, low-friction call-to-action.
- **WhatsApp Formatting**: Strips naked URLs and limits messages to under 300 words.

---

## 3. Simulator Evaluation Results

Tested against the official `judge_simulator.py`:

| Scenario | Status | Result / Score |
| :--- | :--- | :--- |
| **Warmup & Healthz** | `PASS` | All 5 categories + 5 merchants ingested atomically |
| **Auto-Reply Detection** | `PASS` | Detected on Turn 1; cleanly returned `end` |
| **Intent Transition** | `PASS` | Switched to ACTION mode with zero qualifying questions |
| **Hostile Handling** | `PASS` | Returned `end` gracefully on opt-out message |
| **Phase 2 Short Tick** | `PASS` | 46/50 (92%, Excellent) |
| **Full Evaluation (25 Triggers)** | `PASS` | **45/50 (90%, Excellent)** |

### Full Evaluation Dimensions (25 Messages Scored):
- **Avg Specificity**: `10/10` (up from 8/10)
- **Avg Category Fit**: `9/10`
- **Avg Merchant Fit**: `9/10` (up from 8/10)
- **Avg Decision Quality**: `9/10`
- **Avg Engagement**: `8/10`
- **Overall Score**: **45/50 (90% — EXCELLENT)**

---

## 4. Running the Bot & Tests

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start Bot Server
```bash
uvicorn bot:app --host 0.0.0.0 --port 8080
```

### Run Judge Simulator
```bash
# Run all core scenarios
BOT_URL=http://localhost:8080 TEST_SCENARIO=all python judge_simulator.py

# Run Phase 2 short tick
BOT_URL=http://localhost:8080 TEST_SCENARIO=phase2_short python judge_simulator.py

# Run Full Evaluation across all 25 triggers
BOT_URL=http://localhost:8080 TEST_SCENARIO=full_evaluation python judge_simulator.py
```

