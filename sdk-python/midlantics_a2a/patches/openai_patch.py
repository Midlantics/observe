"""Auto-capture OpenAI chat completions with zero code changes in the agent."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..observer import Observer, TraceContext

_COST_PER_1K: dict[str, tuple[float, float]] = {
    # (input $/1K tokens, output $/1K tokens)
    "gpt-4o":            (0.0025, 0.010),
    "gpt-4o-mini":       (0.00015, 0.0006),
    "gpt-4-turbo":       (0.010,  0.030),
    "gpt-4":             (0.030,  0.060),
    "gpt-3.5-turbo":     (0.0005, 0.0015),
    "o1":                (0.015,  0.060),
    "o1-mini":           (0.003,  0.012),
    "o3-mini":           (0.0011, 0.0044),
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    key = next((k for k in _COST_PER_1K if model.startswith(k)), None)
    if not key:
        return None
    inp, out = _COST_PER_1K[key]
    return round((prompt_tokens / 1000 * inp) + (completion_tokens / 1000 * out), 6)


def patch_openai(observer: "Observer", trace: "TraceContext | None" = None) -> None:
    """
    Monkey-patch ``openai.chat.completions.create`` to auto-record every call.

    Pass ``trace`` to attach spans to an existing trace, or omit to create
    a standalone trace per call.

    Usage::

        import openai
        from midlantics_a2a import Observer
        from midlantics_a2a.patches.openai_patch import patch_openai

        obs = Observer(api_url="...", token="...")
        patch_openai(obs)

        # All subsequent openai.chat.completions.create() calls are captured.
    """
    try:
        import openai as _openai
    except ImportError:
        raise ImportError("openai package is required: pip install openai")

    _original_create = _openai.chat.completions.create

    def _patched_create(*args, **kwargs):
        t0 = time.perf_counter()
        error_msg = None
        response = None
        try:
            response = _original_create(*args, **kwargs)
            return response
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            model = kwargs.get("model", "unknown")
            prompt_tokens = completion_tokens = None
            output_content = None

            if response is not None:
                usage = getattr(response, "usage", None)
                if usage:
                    prompt_tokens = getattr(usage, "prompt_tokens", None)
                    completion_tokens = getattr(usage, "completion_tokens", None)
                choices = getattr(response, "choices", [])
                if choices:
                    msg = getattr(choices[0], "message", None)
                    output_content = getattr(msg, "content", None) if msg else None

            cost = None
            if prompt_tokens is not None and completion_tokens is not None:
                cost = _estimate_cost(model, prompt_tokens, completion_tokens)

            ctx = trace or observer.trace(agent_name="openai-auto")
            needs_close = trace is None

            if needs_close:
                ctx.__enter__()

            with ctx.span(f"openai/{model}", kind="llm") as span:
                span.record_llm(
                    model=model,
                    provider="openai",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    input={"messages": kwargs.get("messages")},
                    output={"content": output_content},
                    cost_usd=cost,
                    error=error_msg,
                )

            if needs_close:
                ctx.__exit__(None, None, None)

    _openai.chat.completions.create = _patched_create
