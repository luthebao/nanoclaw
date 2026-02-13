"""Auto-compaction: summarize older messages when approaching context limits."""

from __future__ import annotations


def needs_compaction(prompt_tokens: int, context_window: int, threshold: float) -> bool:
    """Return True when prompt token usage exceeds the threshold ratio."""
    return prompt_tokens >= context_window * threshold


def select_messages_to_compact(messages: list[dict], keep_recent: int = 6) -> tuple[int, int]:
    """Return (start, end) slice indices of messages eligible for compaction.

    Preserves the first message (system prompt) and the last *keep_recent*
    messages.  Returns ``(0, 0)`` when there is nothing worth compacting.
    """
    # First message is the system prompt – always keep it.
    start = 1
    end = len(messages) - keep_recent

    if end <= start:
        return (0, 0)
    return (start, end)


def build_compaction_request(messages_slice: list[dict]) -> list[dict]:
    """Build a summarization prompt from the messages to be compacted.

    Each message is serialised to a short text block.  Tool results longer
    than 2 000 characters are truncated so the summarisation request itself
    stays manageable.
    """
    max_tool_result = 1000
    parts: list[str] = []

    for msg in messages_slice:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # tool results may be long
        if role == "tool":
            name = msg.get("name", "tool")
            text = str(content)
            if len(text) > max_tool_result:
                text = text[:max_tool_result] + "…[truncated]"
            parts.append(f"[tool:{name}] {text}")
        elif role == "assistant":
            # May contain tool_calls alongside content
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                names = ", ".join(tc.get("function", {}).get("name", "?") for tc in tool_calls)
                parts.append(f"[assistant → tool_calls: {names}] {content or ''}")
            else:
                parts.append(f"[assistant] {content or ''}")
        else:
            parts.append(f"[{role}] {content or ''}")

    conversation_text = "\n".join(parts)

    return [
        {
            "role": "system",
            "content": (
                "Summarize the following conversation fragment concisely. "
                "Preserve all key facts, decisions, tool results, and context "
                "the assistant will need to continue the conversation. "
                "Output only the summary, no preamble."
            ),
        },
        {"role": "user", "content": conversation_text},
    ]


def apply_compaction(messages: list[dict], start: int, end: int, summary: str) -> list[dict]:
    """Replace ``messages[start:end]`` with a single user-role summary message."""
    summary_message = {
        "role": "user",
        "content": (f"[Previous conversation summary]\n{summary}"),
    }
    return messages[:start] + [summary_message] + messages[end:]
