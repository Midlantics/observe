"""
Minimal example — just Observe, no policy/firewall/approval.

Use this first to verify your API key works and traces show up in the dashboard
before running the full agent.py demo.

Run:
  python minimal_trace.py

Then go to: https://a2a.midlantics.com/dashboard
You should see a trace named "hello-agent" appear within a few seconds.
Click it → toggle Tree / Waterfall to see the span views.
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# ── SDK import ─────────────────────────────────────────────────────────────────
# Works whether the SDK is installed via pip or checked out locally.
try:
    from midlantics_a2a import Observer
except ImportError:
    # Try the local checkout path relative to this sample folder
    _sdk = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "midlantics", "sdk-python"))
    if os.path.isdir(_sdk):
        sys.path.insert(0, _sdk)
        from midlantics_a2a import Observer
    else:
        print("ERROR: midlantics_a2a not found.")
        print("Either:  pip install midlantics-a2a")
        print("Or clone the sdk-python repo alongside this project.")
        sys.exit(1)

# ── Run ────────────────────────────────────────────────────────────────────────
obs = Observer(
    api_url=os.environ["A2A_API_URL"],
    token=os.environ["A2A_API_KEY"],
)

print("Sending a test trace to your dashboard...")

with obs.trace("hello-agent") as trace:

    with trace.span("step-1-fetch-data", kind="tool") as span:
        time.sleep(0.3)
        span.set_attribute("source", "database")
        span.set_attribute("rows_returned", 42)

    with trace.span("step-2-call-llm", kind="llm") as span:
        time.sleep(0.8)
        span.record_llm(
            model="gpt-4o-mini",
            provider="openai",
            prompt_tokens=150,
            completion_tokens=80,
            cost_usd=0.000068,
            input={"messages": [{"role": "user", "content": "Summarize this data"}]},
            output={"content": "Here is a summary of the 42 rows..."},
        )

    with trace.span("step-3-write-result", kind="tool") as span:
        time.sleep(0.1)
        span.set_attribute("destination", "database")
        span.set_attribute("rows_written", 1)

obs.flush()
print("Done!")
print()
print("→ Go to https://a2a.midlantics.com/dashboard")
print("  Overview → Traces tab → click 'hello-agent'")
print("  Toggle Tree ↔ Waterfall to see the different views.")
