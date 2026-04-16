# midlantics-a2a

Python SDK for [Midlantics A2A](https://a2a.midlantics.com) — agent observability and governance.

## Install

```bash
pip install midlantics-a2a

# With OpenAI auto-capture
pip install "midlantics-a2a[openai]"

# With Anthropic auto-capture
pip install "midlantics-a2a[anthropic]"

# Both
pip install "midlantics-a2a[all]"
```

## Quickstart

```python
from midlantics_a2a import Observer

obs = Observer(
    api_url="https://a2a-api.midlantics.com",
    token="a2a_sk_...",   # generate in dashboard → API Keys
)

with obs.trace("purchase-agent") as trace:
    with trace.span("validate-order", kind="tool") as span:
        result = validate_order(order_id)
        span.set_attribute("order.id", order_id)

    with trace.span("call-llm", kind="llm") as span:
        response = openai_client.chat.completions.create(
            model="gpt-4o", messages=[...]
        )
        span.record_llm(
            model="gpt-4o",
            provider="openai",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
```

## Auto-capture (zero code changes)

```python
from midlantics_a2a import Observer
from midlantics_a2a.patches.openai_patch import patch_openai
import openai

obs = Observer(api_url="...", token="a2a_sk_...")
patch_openai(obs)

# Every openai.chat.completions.create() is now captured automatically
```

```python
from midlantics_a2a.patches.anthropic_patch import patch_anthropic
import anthropic

patch_anthropic(obs)
# Every anthropic.messages.create() is now captured automatically
```

## VPC / self-hosted

Point `api_url` at your self-hosted instance:

```python
obs = Observer(api_url="http://your-internal-host:8000", token="a2a_sk_...")
```

## License

Apache 2.0
