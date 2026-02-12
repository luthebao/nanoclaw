# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Always use `uv` for this Python project:

```bash
# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_tool_validation.py

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Install dependencies
uv sync

# Add/remove packages
uv add <package>
uv remove <package>

# Run the CLI
uv run nanoclaw agent -m "Hello"
uv run nanoclaw gateway
```

## Architecture

### Message Flow

```
Channel (telegram/discord/slack/...) → MessageBus (async queues) → AgentLoop → LLMProvider (via LiteLLM) → Tool execution loop → MessageBus → Channel.send()
```

The **AgentLoop** (`agent/loop.py`) is the core engine: it receives messages from the bus, builds context (system prompt + history + memory + skills), calls the LLM, executes tool calls in a loop (up to `max_tool_iterations`), and publishes responses back. Auto-compaction summarizes older messages when prompt tokens exceed 75% of the context window.

The **MessageBus** (`bus/queue.py`) decouples channels from the agent with inbound/outbound async queues and a subscriber pattern for outbound dispatch.

### Provider System

Registry-driven (`providers/registry.py`): each provider is a `ProviderSpec` dataclass with keywords, env vars, prefixes, and overrides. `LiteLLMProvider` handles model prefixing, gateway detection, and parameter overrides. Config matching: model keywords → first available API key fallback.

### Context Building

`ContextBuilder` (`agent/context.py`) assembles the system prompt from:
1. Identity + runtime info
2. Bootstrap files: `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md` (from workspace)
3. Long-term memory (`memory/MEMORY.md`) + recent daily notes (7 days)
4. Always-loaded skills content
5. Available skills summary (agent uses `read_file` to load on demand)

### Tool System

Tools extend `Tool` ABC (`agent/tools/base.py`) with `name`, `description`, `parameters` (JSON Schema), and async `execute`. Registered in `ToolRegistry`. Built-in: filesystem (read/write/edit/list_dir), shell (exec), web (search/fetch), message, spawn (subagents), cron.

### Skills

YAML frontmatter + Markdown in `nanoclaw/skills/` and `workspace/skills/`. Progressively loaded: summaries in system prompt, full content loaded by agent via `read_file`. `always: true` skills are inlined into the system prompt.

### Sessions

JSONL storage in `~/.nanobot/sessions/`. Key format: `{channel}:{chat_id}`. History capped at 50 messages.

### Subagents

Spawned via `spawn` tool. Isolated context with focused system prompt. No message/spawn tools (prevents recursion). Results announced back via system messages routed through `_process_system_message`.

## Key Conventions

- Python ≥3.11, type hints throughout, Pydantic models for config
- Ruff: line-length 100, rules E/F/I/N/W, E501 ignored
- Config: `~/.nanobot/config.json`, env vars with `NANOCLAW_` prefix
- Workspace: `~/.nanobot/workspace/` (customizable)
- All channel integrations implement `BaseChannel` with `start()`, `stop()`, `send()`
- Provider additions go through `ProviderSpec` in the registry — no if-elif chains
