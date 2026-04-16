"""Auto-capture Anthropic messages.create with zero code changes in the agent."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..observer import Observer, TraceContext

_COST_PER_1K: dict[str, tuple[float, float]] = {
    "claude-opus-4":       (0.015, 0.075),
    "claude-sonnet-4":     (0.003, 0.015),
    "claude-haiku-4":      (0.00025, 0.00125),
    "claude-3-5-sonnet":   (0.003, 0.015),
    "claude-3-5-haiku":    (0.0008, 0.004),
    "claude-3-opus":       (0.015, 0.075),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    key = next((k for k in _COST_PER_1K if model.startswith(k)), None)
    if not key:
        return None
    inp, out = _COST_PER_1K[key]
    return round((input_tokens / 1000 * inp) + (output_tokens / 1000 * out), 6)


def patch_anthropic(observer: "Observer", trace: "TraceContext | None" = None) -> None:
    """
    Monkey-patch ``anthropic.messages.create`` to auto-record every call.

    Usage::

        import anthropic
        from midlantics_a2a import Observer
        from midlantics_a2a.patches.anthropic_patch import patch_anthropic

        obs = Observer(api_url="...", token="...")
        patch_anthropic(obs)
    """
    try:
        import anthropic as _anthropic
    except ImportError:
        raise ImportError("anthropic package is required: pip install anthropic")

    _client_cls = _anthropic.Anthropic
    _original_create = _client_cls.messages.create

    def _patched_create(self_client, *args, **kwargs):
        t0 = time.perf_counter()
        error_msg = None
        response = None
        try:
            response = _original_create(self_client, *args, **kwargs)
            return response
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            model = kwargs.get("model", "unknown")
            input_tokens = output_tokens = None
            output_content = None

            if response is not None:
                usage = getattr(response, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "input_tokens", None)
                    output_tokens = getattr(usage, "output_tokens", None)
                content = getattr(response, "content", [])
                if content:
                    output_content = getattr(content[0], "text", None)

            cost = None
            if input_tokens is not None and output_tokens is not None:
                cost = _estimate_cost(model, input_tokens, output_tokens)

            ctx = trace or observer.trace(agent_name="anthropic-auto")
            needs_close = trace is None

            if needs_close:
                ctx.__enter__()

            with ctx.span(f"anthropic/{model}", kind="llm") as span:
                span.record_llm(
                    model=model,
                    provider="anthropic",
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    input={"messages": kwargs.get("messages"), "system": kwargs.get("system")},
                    output={"content": output_content},
                    cost_usd=cost,
                    error=error_msg,
                )

            if needs_close:
                ctx.__exit__(None, None, None)

    _client_cls.messages.create = _patched_create
