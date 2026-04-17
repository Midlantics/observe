"""
Multi-LLM example — shows how to use the SDK with OpenAI, Anthropic,
DeepSeek, Google Gemini, and any other provider.

Auto-patch support:
  - OpenAI       → patch_openai(obs)   — zero extra lines per call
  - Anthropic    → patch_anthropic(obs) — zero extra lines per call
  - DeepSeek     → uses OpenAI client with base_url, so patch_openai covers it too

For everything else (Gemini, Mistral, Cohere, Ollama, etc.),
record the call manually with span.record_llm() — takes ~3 lines.

Run:
  python llm_providers.py

Set whichever API keys you have in .env:
  OPENAI_API_KEY=sk-...
  ANTHROPIC_API_KEY=sk-ant-...
  DEEPSEEK_API_KEY=sk-...
  GOOGLE_API_KEY=...           (for Gemini)
"""
from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# ── SDK import ─────────────────────────────────────────────────────────────────
try:
    from midlantics_a2a import Observer
    from midlantics_a2a.patches.openai_patch import patch_openai
    from midlantics_a2a.patches.anthropic_patch import patch_anthropic
except ImportError:
    _sdk = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "midlantics", "sdk-python"))
    if os.path.isdir(_sdk):
        sys.path.insert(0, _sdk)
        from midlantics_a2a import Observer
        from midlantics_a2a.patches.openai_patch import patch_openai
        from midlantics_a2a.patches.anthropic_patch import patch_anthropic
    else:
        print("ERROR: midlantics_a2a not found.")
        sys.exit(1)

obs = Observer(
    api_url=os.environ["A2A_API_URL"],
    token=os.environ["A2A_API_KEY"],
    agent_name="multi-llm-demo",
)

PROMPT = "In one sentence, what is the capital of France?"


# ══════════════════════════════════════════════════════════════════════════════
# Option A — OpenAI (auto-patch: zero extra lines per call)
# ══════════════════════════════════════════════════════════════════════════════
def demo_openai():
    if not os.getenv("OPENAI_API_KEY"):
        print("Skipping OpenAI (no OPENAI_API_KEY in .env)")
        return

    from openai import OpenAI

    # Call patch_openai ONCE at startup — all subsequent calls are auto-recorded
    patch_openai(obs)
    oai = OpenAI()

    print("Running OpenAI demo...")
    with obs.trace("openai-demo") as trace:
        with trace.span("call-gpt", kind="llm"):
            # Nothing special here — patch_openai captures tokens, cost, latency automatically
            response = oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": PROMPT}],
            )
            print(f"  GPT-4o-mini: {response.choices[0].message.content}")

    print("  → Dashboard: trace 'openai-demo' with LLM call, tokens, and cost\n")


# ══════════════════════════════════════════════════════════════════════════════
# Option B — Anthropic Claude (auto-patch: same pattern as OpenAI)
# ══════════════════════════════════════════════════════════════════════════════
def demo_anthropic():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Skipping Anthropic (no ANTHROPIC_API_KEY in .env)")
        return

    try:
        import anthropic
    except ImportError:
        print("Skipping Anthropic — install first:  pip install anthropic")
        return

    # Call patch_anthropic ONCE at startup
    patch_anthropic(obs)
    client = anthropic.Anthropic()

    print("Running Anthropic demo...")
    with obs.trace("anthropic-demo") as trace:
        with trace.span("call-claude", kind="llm"):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": PROMPT}],
            )
            print(f"  Claude Haiku: {response.content[0].text}")

    print("  → Dashboard: trace 'anthropic-demo' with tokens and cost\n")


# ══════════════════════════════════════════════════════════════════════════════
# Option C — DeepSeek (auto-patch via OpenAI-compatible client)
# ══════════════════════════════════════════════════════════════════════════════
def demo_deepseek():
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("Skipping DeepSeek (no DEEPSEEK_API_KEY in .env)")
        return

    from openai import OpenAI

    # DeepSeek's API is OpenAI-compatible — same client, different base_url and key.
    # patch_openai patches the global module client and doesn't apply to explicit
    # instances, so we record manually with span.record_llm() (same as Gemini).
    ds = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    print("Running DeepSeek demo...")
    with obs.trace("deepseek-demo") as trace:
        with trace.span("call-deepseek", kind="llm") as span:
            response = ds.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=100,
            )
            content = response.choices[0].message.content
            usage = response.usage
            span.record_llm(
                model="deepseek-chat",
                provider="deepseek",
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                input={"prompt": PROMPT},
                output={"content": content},
            )
            print(f"  DeepSeek: {content}")

    print("  → Dashboard: trace 'deepseek-demo' with tokens and cost\n")


# ══════════════════════════════════════════════════════════════════════════════
# Option D — Google Gemini (manual recording — 3 extra lines)
# ══════════════════════════════════════════════════════════════════════════════
def demo_gemini():
    if not os.getenv("GOOGLE_API_KEY"):
        print("Skipping Gemini (no GOOGLE_API_KEY in .env)")
        return

    try:
        import google.generativeai as genai
    except ImportError:
        print("Skipping Gemini — install first:  pip install google-generativeai")
        return

    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")

    print("Running Gemini demo...")
    with obs.trace("gemini-demo") as trace:
        with trace.span("call-gemini", kind="llm") as span:
            t0 = time.perf_counter()
            response = model.generate_content(PROMPT)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            # Record manually — 3 lines
            usage = response.usage_metadata
            span.record_llm(
                model="gemini-1.5-flash",
                provider="google",
                prompt_tokens=usage.prompt_token_count,
                completion_tokens=usage.candidates_token_count,
                cost_usd=None,      # Gemini pricing varies — set if you know it
                input={"prompt": PROMPT},
                output={"content": response.text},
            )
            print(f"  Gemini Flash: {response.text}")

    print("  → Dashboard: trace 'gemini-demo' with token counts\n")


# ══════════════════════════════════════════════════════════════════════════════
# Option E — Any other provider (Mistral, Cohere, Ollama, Together, etc.)
#             Manual recording — works with any client library
# ══════════════════════════════════════════════════════════════════════════════
def demo_manual_recording():
    """
    Template for any LLM that doesn't have an auto-patch yet.
    Pattern: wrap your call in a span, then call span.record_llm().
    """
    print("Running manual-recording demo (simulated)...")

    with obs.trace("custom-llm-demo") as trace:
        with trace.span("call-my-llm", kind="llm") as span:
            t0 = time.perf_counter()

            # ── Your LLM call goes here ───────────────────────────────────────
            # Examples:
            #   response = mistral_client.chat(model="mistral-small", messages=[...])
            #   response = cohere_client.chat(message=PROMPT, model="command-r")
            #   response = requests.post("http://localhost:11434/api/generate", ...)
            #
            # Simulated:
            time.sleep(0.4)
            fake_response_text = "Paris is the capital of France."
            prompt_tokens = 15
            completion_tokens = 9
            latency_ms = int((time.perf_counter() - t0) * 1000)
            # ─────────────────────────────────────────────────────────────────

            # Record whatever info you have — all fields are optional
            span.record_llm(
                model="my-custom-model",        # required
                provider="my-provider",          # required
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round((prompt_tokens * 0.000001) + (completion_tokens * 0.000002), 6),
                input={"prompt": PROMPT},
                output={"content": fake_response_text},
            )
            print(f"  Custom LLM: {fake_response_text}")

    print("  → Dashboard: trace 'custom-llm-demo' in LLM Calls tab\n")


# ══════════════════════════════════════════════════════════════════════════════
# Option F — Multiple LLMs in one trace (e.g. router pattern)
# ══════════════════════════════════════════════════════════════════════════════
def demo_llm_router():
    """
    Shows how to record a trace that calls multiple LLMs —
    e.g. a cheap model for routing, then a powerful model for the answer.
    All LLM calls appear as separate spans under the same trace.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("Skipping LLM router demo (needs OPENAI_API_KEY)")
        return

    from openai import OpenAI
    oai = OpenAI()

    print("Running LLM router demo...")
    with obs.trace("llm-router-demo") as trace:

        # Step 1: cheap model decides which expensive model to use
        with trace.span("routing-decision", kind="llm") as span:
            t0 = time.perf_counter()
            router_response = oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Reply with just 'simple' or 'complex'."},
                    {"role": "user", "content": f"Is this question simple or complex: {PROMPT}"},
                ],
                max_tokens=5,
            )
            decision = router_response.choices[0].message.content.strip().lower()
            span.set_attribute("routing_decision", decision)

        # Step 2: use the appropriate model
        target_model = "gpt-4o-mini" if decision == "simple" else "gpt-4o"
        with trace.span(f"answer-{target_model}", kind="llm"):
            final_response = oai.chat.completions.create(
                model=target_model,
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=100,
            )
            print(f"  Router chose: {target_model}")
            print(f"  Answer: {final_response.choices[0].message.content}")

    print("  → Dashboard: trace 'llm-router-demo' — 2 LLM spans, cost breakdown\n")


# ══════════════════════════════════════════════════════════════════════════════
# Run all demos
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Multi-LLM demo — watch results at https://a2a.midlantics.com/dashboard\n")
    print("─" * 60)

    demo_openai()
    demo_anthropic()
    demo_deepseek()
    demo_gemini()
    demo_manual_recording()
    demo_llm_router()

    obs.flush()
    print("Done. Check Dashboard → Overview → LLM Calls tab for all recorded calls.")
    print("Each provider shows separately with token counts and cost.")
