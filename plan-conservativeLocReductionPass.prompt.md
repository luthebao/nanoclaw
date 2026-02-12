## Plan: Conservative LOC Reduction Pass (DRAFT)

This plan targets low-risk LOC reduction with functional compatibility (your choices: Conservative depth, Functional compatibility, Targeted verification), prioritizing CLI/Daemon, Channels, Agent Core, and Tools. The approach focuses on structural deduplication where behavior is already repeated: command wrappers, lifecycle loops, repeated context wiring, and tool boilerplate. Deep/high-risk redesigns (like provider-schema unification and heavy Mochat internals) are intentionally deferred. Expected first-pass reduction is roughly 220–430 LOC while preserving runtime behavior and command semantics.

**Steps**

1. Baseline and guardrails: capture current command behavior for gateway/channels/cron and document expected outputs from [nanoclaw/cli/commands.py](nanoclaw/cli/commands.py) and daemon backends [nanoclaw/daemon/launchd.py](nanoclaw/daemon/launchd.py), [nanoclaw/daemon/systemd.py](nanoclaw/daemon/systemd.py).
2. Refactor gateway command wrappers into one shared helper (`run_daemon_action`) in [nanoclaw/cli/commands.py](nanoclaw/cli/commands.py), replacing repeated try/except and status printing paths.
3. Deduplicate daemon subprocess wrappers by introducing one internal exec helper reused by `_launchctl` and `_systemctl` in [nanoclaw/daemon/launchd.py](nanoclaw/daemon/launchd.py) and [nanoclaw/daemon/systemd.py](nanoclaw/daemon/systemd.py).
4. Collapse duplicated AgentLoop tool-context setup into one method used by both message paths in [nanoclaw/agent/loop.py](nanoclaw/agent/loop.py) (`_process_message`, `_process_system_message` callsites).
5. Convert channel initialization to a data-driven registry loop in [nanoclaw/channels/manager.py](nanoclaw/channels/manager.py), preserving optional-import behavior and channel-specific constructor args.
6. Extract shared filesystem-tool guards (path resolve/validation/error shaping) into a base helper and reuse across tools in [nanoclaw/agent/tools/filesystem.py](nanoclaw/agent/tools/filesystem.py).
7. Standardize static tool metadata declarations (`name`, `description`, `parameters`) via a lightweight shared pattern across [nanoclaw/agent/tools/shell.py](nanoclaw/agent/tools/shell.py), [nanoclaw/agent/tools/cron.py](nanoclaw/agent/tools/cron.py), [nanoclaw/agent/tools/message.py](nanoclaw/agent/tools/message.py), [nanoclaw/agent/tools/spawn.py](nanoclaw/agent/tools/spawn.py).
8. Introduce a minimal reconnect-runner utility for channels with near-identical run/retry loops and apply only to lowest-risk pairs first (Discord + WhatsApp) in [nanoclaw/channels/discord.py](nanoclaw/channels/discord.py) and [nanoclaw/channels/whatsapp.py](nanoclaw/channels/whatsapp.py); defer Mochat.
9. Simplify channel status table row assembly with data-driven rendering in [nanoclaw/cli/commands.py](nanoclaw/cli/commands.py) (`channels_status`) without changing displayed fields.
10. Stop-point review: report LOC delta, changed surfaces, and deferred medium/high-risk items (Mochat deep dedup, provider/config coupling).

**Verification**

- Run lint/tests baseline and post-refactor: `uv run ruff check .`, `uv run pytest` (if tests exist).
- Targeted CLI smoke: `uv run nanoclaw gateway status`, `uv run nanoclaw gateway start`, `uv run nanoclaw channels status`, `uv run nanoclaw cron list`.
- Functional parity checks for Agent loop tool execution ordering and channel initialization (no import regressions for optional SDKs).
- Manual sanity for daemon command error paths on macOS launchd (no message regressions that affect usability).

**Decisions**

- Chose low-risk dedup first over architectural rewrites to maximize LOC reduction per risk.
- Deferred high-risk refactors in provider/schema and Mochat internals for a later phase.
- Preserved functional behavior as the compatibility contract; minor non-critical wording drift is allowed.
