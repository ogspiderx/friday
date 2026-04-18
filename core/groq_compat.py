"""
Groq chat.completions wrapper with model fallback when a model emits invalid tool calls.
"""

from __future__ import annotations

from typing import Any, Callable

from groq import Groq


def _is_tool_or_bad_request(err: BaseException) -> bool:
    s = str(err).lower()
    return any(
        x in s
        for x in (
            "tool_use_failed",
            "tool choice",
            "invalid_request",
            "called a tool",
            "failed_generation",
        )
    )


def chat_completion_create(
    client: Groq,
    *,
    primary_model: str,
    builder: Callable[[str], dict[str, Any]],
) -> Any:
    """
    Run chat.completions.create; on tool/schema errors retry with safer models (Llama).

    builder(model_id) -> kwargs for create (messages, temperature, etc.); model may be omitted.
    """
    from config.settings import get_settings

    settings = get_settings()
    chain: list[str] = [primary_model]
    for mid in (settings.model_router.strong_model, settings.model_router.fast_model):
        if mid and mid not in chain:
            chain.append(mid)

    last_exc: BaseException | None = None
    for mid in chain:
        kwargs = dict(builder(mid))
        kwargs["model"] = mid
        for k in ("tools", "tool_choice", "parallel_tool_calls"):
            kwargs.pop(k, None)
        try:
            return client.chat.completions.create(**kwargs)
        except BaseException as e:
            last_exc = e
            if _is_tool_or_bad_request(e) and mid != chain[-1]:
                continue
            if not _is_tool_or_bad_request(e):
                raise
            if mid == chain[-1]:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("chat_completion_create: empty model chain")
