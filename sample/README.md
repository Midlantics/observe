# Midlantics A2A — Sample Agent

A working customer support agent that demonstrates all four platform features:
Observe, Policy Engine, Approval Layer, and Firewall.

## Files

| File | What it does |
|---|---|
| `minimal_trace.py` | **Start here** — sends one trace to verify your key works |
| `agent.py` | Full demo with all 4 features wired together |
| `test_firewall.py` | Firewall test — 7 different inputs, see what gets blocked |
| `test_approval.py` | Creates one approval request; you approve/reject in the dashboard |
| `setup_policies.py` | Creates the 3 policies the agent demo needs (run once) |
| `a2a_clients.py` | HTTP wrappers for Policy, Firewall, Approval (no SDK needed) |
| `llm_providers.py` | Multi-LLM demo — OpenAI, Anthropic, DeepSeek, Gemini, and any other provider |

---

## Quick Start

### 1. Get your API key

1. Go to **https://a2a.midlantics.com/dashboard/settings**
2. Click **Create API key**, give it a name like `local-test`
3. Copy the key — it starts with `a2a_sk_` and is shown **only once**

### 2. Create your .env file

```bash
cp .env.example .env
```

Open `.env` and fill in:
```
A2A_API_KEY=a2a_sk_...       ← paste your key here
A2A_API_URL=https://a2a-api.midlantics.com
OPENAI_API_KEY=sk-...        ← for agent.py and llm_providers.py
```

Add whichever LLM keys you have (all optional, only needed for `llm_providers.py`):
```
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
GOOGLE_API_KEY=...
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

That installs the core 3 packages (`openai`, `httpx`, `python-dotenv`).
No Supabase SDK, no extra auth steps.

For the extra LLM demos in `llm_providers.py`, install only what you need:
```bash
pip install anthropic              # for Anthropic / Claude
pip install google-generativeai    # for Google Gemini
# DeepSeek uses the openai package — nothing extra needed
```

### 4. Verify it works

```bash
python minimal_trace.py
```

Go to **Dashboard → Overview → Traces tab**.
A trace named `hello-agent` should appear within a few seconds.
Click it and toggle **Tree ↔ Waterfall** to see the two views.

---

## Running the Full Demo

### Step 1 — Create policies (one time)

```bash
python setup_policies.py
```

Creates 3 policies in your workspace:
- **Block competitor domains** — blocks `send_email` to `@competitor.com`
- **Flag large refunds** — flags when `refund_amount > 500`
- **Block dangerous actions** — blocks `delete_record`, flags `export_data`

Check them at **Dashboard → Policy Engine**.

### Step 2 — Run the agent

```bash
python agent.py
```

Runs 3 test cases automatically:

**Case 1 — Normal email, $49.99 refund**
- Firewall: clean
- Policy: allow (under $500 threshold)
- Sends successfully
- Dashboard: Overview → Traces → 5-span trace with tool + LLM calls

**Case 2 — Enterprise email, $1,200 refund**
- Firewall: clean
- Policy: flagged (amount > $500)
- Agent pauses at the approval gate
- **Open Dashboard → Approval and click Approve or Reject**
- Or check your email for one-click links
- Agent resumes when you decide

**Case 3 — Prompt injection attempt**
- Firewall: BLOCKED immediately
- Agent returns early, never touches OpenAI
- Dashboard: Firewall → Events → blocked scan

---

## Standalone Tests

```bash
# 7 inputs — clean, injection, jailbreak, SSN, CC, exfiltration, email
python test_firewall.py

# Creates 1 approval request, waits for your click in the dashboard
python test_approval.py
```

---

## What the Dashboard Shows

**Overview → Traces**
Click any trace → **Tree view** shows span hierarchy · **Waterfall view** shows timing.
Span colors: purple = LLM · blue = tool · amber = agent · pink = handoff

**Policy Engine → Evaluation log**
Every `policy.evaluate()` call logged. Green = allow · amber = flag · red = block.

**Approval**
Pending requests with countdown timers. Click Approve / Reject (or use email links).

**Firewall → Events**
Every scan logged with threat types. Raw content is never stored — only a hash.

---

## Match Condition Reference

When adding rules in the dashboard, the `match` dict supports:

| Format | Example | Meaning |
|---|---|---|
| `field: value` | `action_type: send_email` | Regex match against that field |
| `field_gt: N` | `refund_amount_gt: 500` | Numeric greater-than |
| `field_lt: N` | `refund_amount_lt: 10` | Numeric less-than |
| `output_contains: pattern` | `output_contains: \d{3}-\d{2}-\d{4}` | Regex across all payload values |

Nested payload dicts are flattened to dot notation:
`{"user": {"email": "x"}}` → matched as `user.email`.

---

## Using Different LLM Providers

Run the multi-LLM demo to see every provider in action:

```bash
python llm_providers.py
```

| Provider | How it works | Extra install |
|---|---|---|
| **OpenAI** | `patch_openai(obs)` once — all calls auto-recorded | none |
| **Anthropic / Claude** | `patch_anthropic(obs)` once — all calls auto-recorded | `pip install anthropic` |
| **DeepSeek** | Same OpenAI client, custom `base_url` — manual `span.record_llm()` | none |
| **Google Gemini** | Manual `span.record_llm()` — 3 extra lines | `pip install google-generativeai` |
| **Mistral / Cohere / Ollama / any other** | Manual `span.record_llm()` — works with any HTTP client | none |

### Anthropic

```python
from midlantics_a2a.patches.anthropic_patch import patch_anthropic
import anthropic

patch_anthropic(obs)          # call once at startup
client = anthropic.Anthropic()

with obs.trace("my-trace") as trace:
    with trace.span("call-claude", kind="llm"):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": "Hello!"}],
        )
```

### DeepSeek

DeepSeek's API is OpenAI-compatible, so you use the `openai` package with a custom `base_url`. `patch_openai` automatically records the call — no extra steps.

```python
from openai import OpenAI
from midlantics_a2a.patches.openai_patch import patch_openai

patch_openai(obs)             # call once at startup
ds = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

with obs.trace("my-trace") as trace:
    with trace.span("call-deepseek", kind="llm"):
        response = ds.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "Hello!"}],
        )
```

### Any other provider

For any provider not listed above, wrap your call in a span and call `span.record_llm()`:

```python
with obs.trace("my-trace") as trace:
    with trace.span("call-my-llm", kind="llm") as span:
        response = my_client.generate(prompt="Hello!")   # your real call here

        span.record_llm(
            model="my-model",          # required
            provider="my-provider",    # required
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            cost_usd=None,             # optional
            input={"prompt": "Hello!"},
            output={"content": response.text},
        )
```

---

## Adapting to Your Agent

Replace the two simulated functions in `agent.py` with your real ones:

```python
def search_knowledge_base(query: str) -> str:
    # Replace with your vector DB / search API call
    return your_vector_db.search(query)

def send_email(to: str, body: str) -> bool:
    # Replace with your SMTP / Resend / SendGrid call
    return your_email_client.send(to=to, body=body)
```

Everything else — tracing, policy checks, firewall scans, approval gates — stays identical.


*2026 Copyright Midlantics — midlantics.com platforms — Build something people need.*