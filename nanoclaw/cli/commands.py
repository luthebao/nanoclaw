"""CLI commands for nanoclaw."""

import asyncio
import os
import select
import shutil
import signal
import sys
from pathlib import Path

import typer
from InquirerPy.prompts.list import ListPrompt
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from nanoclaw import __logo__, __version__

app = typer.Typer(
    name="nanoclaw",
    help=f"{__logo__} nanoclaw - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios

        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from nanoclaw.utils.helpers import get_data_path

    history_file = get_data_path() / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,  # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} nanoclaw[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} nanoclaw v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True),
):
    """nanoclaw - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


def _step_action(title: str, desc: str) -> bool:
    """Inline arrow-key selection for a wizard step. Returns True to configure."""
    result = ListPrompt(
        message=f"{title} - {desc}",
        choices=[
            {"name": "Configure", "value": True},
            {"name": "Skip", "value": False},
        ],
        default=False,
    ).execute()
    return result


@app.command()
def onboard():
    """Initialize nanoclaw configuration and workspace."""
    from nanoclaw.config.loader import get_config_path, save_config
    from nanoclaw.config.schema import Config
    from nanoclaw.utils.helpers import get_workspace_path

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not typer.confirm("Overwrite?"):
            raise typer.Exit()

    # Create default config
    config = Config()

    # Interactive step-by-step configuration
    console.print(f"\n{__logo__} Configure your nanoclaw:\n")

    steps = [
        ("Step 1/5: Agents", "Model, workspace, defaults", _configure_agents),
        ("Step 2/5: Providers", "API keys for LLM providers", _configure_providers),
        ("Step 3/5: Channels", "Telegram, Discord, Slack, etc.", _configure_channels),
        ("Step 4/5: Gateway", "Host and port", _configure_gateway),
        ("Step 5/5: Heartbeat", "Interval and toggle", _configure_heartbeat),
    ]

    for title, desc, configure_fn in steps:
        if _step_action(title, desc):
            configure_fn(config)
        else:
            console.print(f"  [dim]Skipped {title}[/dim]")
        console.print()

    save_config(config)
    console.print(f"[green]✓[/green] Created config at {config_path}")

    # Create workspace
    workspace = get_workspace_path()
    console.print(f"[green]✓[/green] Created workspace at {workspace}")

    # Create default bootstrap files
    _create_workspace_templates(workspace)

    console.print(f"\n{__logo__} nanoclaw is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.nanoclaw/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print('  2. Chat: [cyan]nanoclaw agent -m "Hello!"[/cyan]')
    console.print(
        "\n[dim]Want Telegram/WhatsApp? See: https://github.com/luthebao/nanoclaw#-chat-apps[/dim]"
    )


def _configure_agents(config):
    """Prompt for agent defaults."""
    d = config.agents.defaults
    d.model = typer.prompt("  Model", default=d.model)
    d.workspace = typer.prompt("  Workspace", default=d.workspace)
    d.max_tokens = int(typer.prompt("  Max tokens", default=str(d.max_tokens)))
    d.temperature = float(typer.prompt("  Temperature", default=str(d.temperature)))
    console.print("[green]✓[/green] Agents configured")


def _configure_channels(config):
    """Prompt for channel configuration via sub-menu."""
    channel_names = [
        ("telegram", "Telegram"),
        ("discord", "Discord"),
        ("slack", "Slack"),
        ("whatsapp", "WhatsApp"),
        ("feishu", "Feishu"),
        ("dingtalk", "DingTalk"),
        ("email", "Email"),
        ("mochat", "Mochat"),
        ("qq", "QQ"),
    ]
    while True:
        choices = []
        for key, label in channel_names:
            ch = getattr(config.channels, key)
            status = "on" if ch.enabled else "off"
            choices.append({"name": f"{label} ({status})", "value": key})
        choices.append({"name": "Back", "value": None})
        pick = ListPrompt(
            message="Select channel:",
            choices=choices,
            default=None,
        ).execute()
        if pick is None:
            break
        key = pick
        label = next(name for k, name in channel_names if k == key)
        ch = getattr(config.channels, key)
        enabled_str = typer.prompt(f"  {label} enabled? (y/n)", default="y" if ch.enabled else "n")
        ch.enabled = enabled_str.lower() in ("y", "yes", "true", "1")
        # Prompt for key credential fields based on channel type
        if hasattr(ch, "token") and key != "discord":
            ch.token = typer.prompt(f"  {label} token", default=ch.token or "")
        if hasattr(ch, "token") and key == "discord":
            ch.token = typer.prompt(f"  {label} bot token", default=ch.token or "")
        if hasattr(ch, "bot_token") and key == "slack":
            ch.bot_token = typer.prompt(
                f"  {label} bot token (xoxb-...)", default=ch.bot_token or ""
            )
            ch.app_token = typer.prompt(
                f"  {label} app token (xapp-...)", default=ch.app_token or ""
            )
        if hasattr(ch, "app_id") and key == "feishu":
            ch.app_id = typer.prompt(f"  {label} app_id", default=ch.app_id or "")
            ch.app_secret = typer.prompt(f"  {label} app_secret", default=ch.app_secret or "")
        if hasattr(ch, "client_id") and key == "dingtalk":
            ch.client_id = typer.prompt(f"  {label} client_id", default=ch.client_id or "")
            ch.client_secret = typer.prompt(
                f"  {label} client_secret", default=ch.client_secret or ""
            )
        if hasattr(ch, "app_id") and key == "qq":
            ch.app_id = typer.prompt(f"  {label} app_id", default=ch.app_id or "")
            ch.secret = typer.prompt(f"  {label} secret", default=ch.secret or "")
        console.print(f"  [green]✓[/green] {label} configured")
        console.print()


def _configure_providers(config):
    """Prompt for provider API keys via sub-menu."""
    from nanoclaw.providers.registry import PROVIDERS

    while True:
        choices = []
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            has_key = bool(p and p.api_key)
            status = "set" if has_key else "not set"
            choices.append({"name": f"{spec.label} ({status})", "value": spec.name})
        choices.append({"name": "Back", "value": None})
        pick = ListPrompt(
            message="Select provider:",
            choices=choices,
            default=None,
        ).execute()
        if pick is None:
            break
        spec = next(s for s in PROVIDERS if s.name == pick)
        p = getattr(config.providers, spec.name)
        p.api_key = typer.prompt(f"  {spec.label} API key", default=p.api_key or "")
        default_base = p.api_base or spec.default_api_base or ""
        base = typer.prompt(f"  {spec.label} API base URL", default=default_base)
        p.api_base = base if base else None
        console.print(f"  [green]✓[/green] {spec.label} configured")
        console.print()


def _configure_gateway(config):
    """Prompt for gateway settings."""
    g = config.gateway
    g.host = typer.prompt("  Host", default=g.host)
    g.port = int(typer.prompt("  Port", default=str(g.port)))
    console.print("[green]✓[/green] Gateway configured")


def _configure_heartbeat(config):
    """Prompt for heartbeat settings."""
    h = config.heartbeat
    enabled_str = typer.prompt("  Enabled? (y/n)", default="y" if h.enabled else "n")
    h.enabled = enabled_str.lower() in ("y", "yes", "true", "1")
    h.interval_s = int(typer.prompt("  Interval (seconds)", default=str(h.interval_s)))
    console.print("[green]✓[/green] Heartbeat configured")


def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in your memory files

## Interactive Choice Formatting

When presenting multiple-choice options or asking the user to select from choices, use these formats to enable clickable button UI on supported channels (Telegram, etc.):

### Letter choices (preferred)
```
A) First option
B) Second option
C) Third option
D) Fourth option
```

### Numbered choices
```
1) First option
2) Second option
3) Third option
```

### Yes/No questions
Use phrases like "yes/no", "type yes or no", or end with "confirm?" to trigger Yes/No buttons.

### Inline prompts
You can also use phrases like:
- "Type A/B/C/D to proceed"
- "Choose one: A - Option1, B - Option2"

**Note:** For "other" or custom input options, just say "or type your answer" - the user can still type freely.
""",
        "SOUL.md": """# Soul

I am nanoclaw, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
    }

    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")

    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text(
            """# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
"""
        )
        console.print("  [dim]Created memory/MEMORY.md[/dim]")

    # Create skills directory for custom user skills
    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)

    # Copy built-in skills to workspace (skip existing to preserve customizations)
    from nanoclaw.agent.skills import BUILTIN_SKILLS_DIR

    if BUILTIN_SKILLS_DIR.exists():
        for skill_dir in BUILTIN_SKILLS_DIR.iterdir():
            if skill_dir.is_dir():
                target = skills_dir / skill_dir.name
                if not target.exists():
                    shutil.copytree(skill_dir, target)
                    console.print(f"  [dim]Installed skill: {skill_dir.name}[/dim]")


def _make_provider(config):
    """Create LiteLLMProvider from config. Exits if no API key found."""
    from nanoclaw.providers.litellm_provider import LiteLLMProvider

    p = config.get_provider()
    model = config.agents.defaults.model
    if not (p and p.api_key) and not model.startswith("bedrock/"):
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ~/.nanoclaw/config.json under providers section")
        raise typer.Exit(1)
    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )


# ============================================================================
# Gateway / Server
# ============================================================================

gateway_app = typer.Typer(invoke_without_command=True, help="Manage the nanoclaw gateway service")
app.add_typer(gateway_app, name="gateway")


def _try_connect_agent(host: str, port: int) -> bool:
    """Check if the agent daemon is reachable on the given TCP port."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def _run_gateway_foreground(port: int, verbose: bool) -> None:
    """Start the gateway in the foreground."""
    from nanoclaw.channels.manager import ChannelManager
    from nanoclaw.config.loader import get_data_dir, load_config
    from nanoclaw.cron.service import CronService
    from nanoclaw.cron.types import CronJob
    from nanoclaw.heartbeat.service import HeartbeatService
    from nanoclaw.session.manager import SessionManager

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{__logo__} Starting nanoclaw gateway on port {port}...")

    config = load_config()
    session_manager = SessionManager(config.workspace_path)

    agent_host = config.agent_service.host
    agent_port = config.agent_service.port
    use_network = _try_connect_agent(agent_host, agent_port)

    # Decide bus mode: network (agent daemon running) or in-process (fallback)
    from nanoclaw.agent.loop import AgentLoop
    from nanoclaw.bus.network import NetworkBusClient
    from nanoclaw.bus.queue import MessageBus

    agent = None
    provider = None
    bus: MessageBus | NetworkBusClient
    if use_network:
        console.print(f"[green]✓[/green] Agent daemon detected at {agent_host}:{agent_port}")
        bus = NetworkBusClient(agent_host, agent_port)
    else:
        console.print("[yellow]Agent daemon not running, using in-process mode[/yellow]")
        bus = MessageBus()
        provider = _make_provider(config)

    # Create cron service
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if not use_network and isinstance(bus, MessageBus):
        # In-process mode: create agent with cron service
        assert provider is not None
        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            model=config.agents.defaults.model,
            max_iterations=config.agents.defaults.max_tool_iterations,
            brave_api_key=config.tools.web.search.api_key or None,
            exec_config=config.tools.exec,
            cron_service=cron,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            session_manager=session_manager,
            context_window=config.agents.defaults.context_window,
            compaction_threshold=config.agents.defaults.compaction_threshold,
        )

    # Set cron callback
    if agent:
        # In-process: call agent directly
        async def on_cron_job(job: CronJob) -> str | None:
            response = await agent.process_direct(
                job.payload.message,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
            if job.payload.deliver and job.payload.to and isinstance(bus, MessageBus):
                from nanoclaw.bus.events import OutboundMessage

                await bus.publish_outbound(
                    OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=response or "",
                    )
                )
            return response
    else:
        # Network mode: dispatch through the bus
        async def on_cron_job(job: CronJob) -> str | None:
            from nanoclaw.bus.events import InboundMessage

            await bus.publish_inbound(
                InboundMessage(
                    channel=job.payload.channel or "cron",
                    sender_id="cron",
                    chat_id=job.payload.to or f"cron:{job.id}",
                    content=job.payload.message,
                )
            )
            return None

    cron.on_job = on_cron_job

    # Create heartbeat service
    if agent:

        async def on_heartbeat(prompt: str) -> str:
            return await agent.process_direct(prompt, session_key="heartbeat")
    else:

        async def on_heartbeat(prompt: str) -> str:
            from nanoclaw.bus.events import InboundMessage

            await bus.publish_inbound(
                InboundMessage(
                    channel="heartbeat",
                    sender_id="heartbeat",
                    chat_id="heartbeat",
                    content=prompt,
                )
            )
            return ""

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=config.heartbeat.interval_s,
        enabled=config.heartbeat.enabled,
    )

    # Create channel manager
    channels = ChannelManager(config, bus, session_manager=session_manager)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    if config.heartbeat.enabled:
        interval_min = config.heartbeat.interval_s // 60
        console.print(f"[green]✓[/green] Heartbeat: every {interval_min}m")
    else:
        console.print("[yellow]⊘[/yellow] Heartbeat: disabled")

    async def run():
        try:
            if use_network and isinstance(bus, NetworkBusClient):
                await bus.connect()
            await cron.start()
            await heartbeat.start()
            tasks = [channels.start_all()]
            if agent:
                tasks.append(agent.run())
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            console.print("\nShutting down...")
            heartbeat.stop()
            cron.stop()
            if agent:
                agent.stop()
            bus.stop()
            await channels.stop_all()

    asyncio.run(run())


@gateway_app.callback()
def gateway_callback(
    ctx: typer.Context,
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the nanoclaw gateway (foreground by default)."""
    ctx.ensure_object(dict)
    ctx.obj["port"] = port
    ctx.obj["verbose"] = verbose
    if ctx.invoked_subcommand is None:
        _run_gateway_foreground(port, verbose)


@gateway_app.command("run")
def gateway_run(ctx: typer.Context):
    """Run the gateway in the foreground (used by daemon service file)."""
    _run_gateway_foreground(ctx.obj["port"], ctx.obj["verbose"])


def _run_daemon_action(action: str, success_msg: str) -> None:
    """Run a daemon manager action with standard error handling."""
    try:
        dm = _get_daemon_manager()
        getattr(dm, action)()
        console.print(f"[green]✓[/green] {success_msg}")
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@gateway_app.command("install")
def gateway_install():
    """Install the gateway as an OS background service."""
    try:
        dm = _get_daemon_manager()
        service_file = dm.install()
        console.print(f"[green]✓[/green] Service installed: {service_file}")
        console.print("Start with: [cyan]nanoclaw gateway start[/cyan]")
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@gateway_app.command("uninstall")
def gateway_uninstall():
    """Remove the gateway OS background service."""
    _run_daemon_action("uninstall", "Service uninstalled")


@gateway_app.command("start")
def gateway_start():
    """Start the gateway daemon via the OS service manager."""
    _run_daemon_action("start", "Gateway daemon started")


@gateway_app.command("stop")
def gateway_stop():
    """Stop the gateway daemon."""
    _run_daemon_action("stop", "Gateway daemon stopped")


@gateway_app.command("restart")
def gateway_restart():
    """Restart the gateway daemon."""
    _run_daemon_action("restart", "Gateway daemon restarted")


@gateway_app.command("status")
def gateway_status():
    """Show gateway daemon status."""
    try:
        dm = _get_daemon_manager()
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    info = dm.get_info()
    log_out, log_err = dm.log_paths()

    table = Table(title="Gateway Daemon Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Service", info.name)
    table.add_row("Installed", "[green]yes[/green]" if info.installed else "[red]no[/red]")
    table.add_row("Running", "[green]yes[/green]" if info.running else "[dim]no[/dim]")
    table.add_row("PID", str(info.pid) if info.pid else "-")
    table.add_row("Service file", str(info.service_file) if info.service_file else "-")
    table.add_row("Stdout log", str(log_out))
    table.add_row("Stderr log", str(log_err))

    console.print(table)


@gateway_app.command("logs")
def gateway_logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    stderr: bool = typer.Option(False, "--stderr", "-e", help="Show stderr log instead"),
):
    """Tail gateway log files."""
    import subprocess as sp

    dm = _get_daemon_manager()
    log_out, log_err = dm.log_paths()
    log_file = log_err if stderr else log_out

    if not log_file.exists():
        console.print(f"[yellow]Log file not found:[/yellow] {log_file}")
        console.print("Has the gateway been started as a daemon?")
        raise typer.Exit(1)

    cmd = ["tail", f"-n{lines}"]
    if follow:
        cmd.append("-f")
    cmd.append(str(log_file))

    try:
        sp.run(cmd)
    except KeyboardInterrupt:
        pass


def _get_daemon_manager():
    """Create a DaemonManager, loading config for env_passthrough."""
    from nanoclaw.config.loader import load_config
    from nanoclaw.daemon import DaemonManager

    config = load_config()
    return DaemonManager(
        extra_env_passthrough=config.daemon.env_passthrough,
    )


# ============================================================================
# Agent Commands
# ============================================================================

agent_app = typer.Typer(invoke_without_command=True, help="Manage the nanoclaw agent service")
app.add_typer(agent_app, name="agent")


def _run_agent_foreground() -> None:
    """Run the agent as a standalone daemon (network bus server)."""
    from nanoclaw.agent.loop import AgentLoop
    from nanoclaw.bus.network import NetworkBusServer
    from nanoclaw.config.loader import get_data_dir, load_config
    from nanoclaw.cron.service import CronService
    from nanoclaw.session.manager import SessionManager

    config = load_config()
    host = config.agent_service.host
    port = config.agent_service.port

    console.print(f"{__logo__} Starting nanoclaw agent on {host}:{port}...")

    server = NetworkBusServer(host, port)
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    agent_loop = AgentLoop(
        bus=server,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        context_window=config.agents.defaults.context_window,
        compaction_threshold=config.agents.defaults.compaction_threshold,
    )

    console.print("[green]✓[/green] Agent ready, waiting for gateway connections...")

    async def run():
        try:
            await cron.start()
            await asyncio.gather(server.serve(), agent_loop.run())
        except KeyboardInterrupt:
            console.print("\nShutting down agent...")
            cron.stop()
            agent_loop.stop()
            server.stop()

    asyncio.run(run())


@agent_app.callback()
def agent_callback(
    ctx: typer.Context,
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(
        False, "--logs/--no-logs", help="Show nanoclaw runtime logs during chat"
    ),
):
    """Interact with the agent directly, or manage the agent daemon service."""
    ctx.ensure_object(dict)
    ctx.obj["message"] = message
    ctx.obj["session_id"] = session_id
    ctx.obj["markdown"] = markdown
    ctx.obj["logs"] = logs
    if ctx.invoked_subcommand is None:
        # No subcommand → interactive/single-message mode (original behavior)
        _agent_interactive(message, session_id, markdown, logs)


def _agent_interactive(message: str | None, session_id: str, markdown: bool, logs: bool) -> None:
    """Run agent in interactive or single-message mode (original behavior)."""
    from loguru import logger

    from nanoclaw.agent.loop import AgentLoop
    from nanoclaw.bus.queue import MessageBus
    from nanoclaw.config.loader import load_config

    config = load_config()

    bus = MessageBus()
    provider = _make_provider(config)

    if logs:
        logger.enable("nanoclaw")
    else:
        logger.disable("nanoclaw")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        context_window=config.agents.defaults.context_window,
        compaction_threshold=config.agents.defaults.compaction_threshold,
    )

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext

            return nullcontext()
        return console.status("[dim]nanoclaw is thinking...[/dim]", spinner="dots")

    if message:

        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id)
            _print_agent_response(response, render_markdown=markdown)

        asyncio.run(run_once())
    else:
        _init_prompt_session()
        console.print(
            f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
        )

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            while True:
                try:
                    _flush_pending_tty_input()
                    user_input = await _read_interactive_input_async()
                    command = user_input.strip()
                    if not command:
                        continue

                    if _is_exit_command(command):
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break

                    with _thinking_ctx():
                        response = await agent_loop.process_direct(user_input, session_id)
                    _print_agent_response(response, render_markdown=markdown)
                except KeyboardInterrupt:
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break
                except EOFError:
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break

        asyncio.run(run_interactive())


@agent_app.command("serve")
def agent_serve():
    """Run the agent as a TCP server in the foreground."""
    _run_agent_foreground()


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanoclaw.config.loader import load_config

    config = load_config()

    ch = config.channels
    _dim = "[dim]not configured[/dim]"
    rows = [
        ("WhatsApp", ch.whatsapp, ch.whatsapp.bridge_url),
        ("Discord", ch.discord, ch.discord.gateway_url),
        ("Feishu", ch.feishu, f"app_id: {ch.feishu.app_id[:10]}..." if ch.feishu.app_id else _dim),
        ("Mochat", ch.mochat, ch.mochat.base_url or _dim),
        (
            "Telegram",
            ch.telegram,
            f"token: {ch.telegram.token[:10]}..." if ch.telegram.token else _dim,
        ),
        ("Slack", ch.slack, "socket" if ch.slack.app_token and ch.slack.bot_token else _dim),
    ]

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")
    for name, cfg, detail in rows:
        table.add_row(name, "✓" if cfg.enabled else "✗", detail)
    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    from nanoclaw.utils.helpers import get_data_path

    user_bridge = get_data_path() / "bridge"

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanoclaw/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall nanoclaw-ai")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess

    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from nanoclaw.config.loader import get_data_dir
    from nanoclaw.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    jobs = service.list_jobs(include_disabled=all)

    if not jobs:
        console.print("No scheduled jobs.")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")

    import time

    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = job.schedule.expr or ""
        else:
            sched = "one-time"

        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            next_time = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(job.state.next_run_at_ms / 1000)
            )
            next_run = next_time

        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"

        table.add_row(job.id, job.name, sched, status, next_run)

    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(
        None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"
    ),
):
    """Add a scheduled job."""
    from nanoclaw.config.loader import get_data_dir
    from nanoclaw.cron.service import CronService
    from nanoclaw.cron.types import CronSchedule

    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr)
    elif at:
        import datetime

        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        to=to,
        channel=channel,
    )

    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from nanoclaw.config.loader import get_data_dir
    from nanoclaw.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from nanoclaw.config.loader import get_data_dir
    from nanoclaw.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from nanoclaw.config.loader import get_data_dir
    from nanoclaw.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print("[green]✓[/green] Job executed")
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanoclaw status."""
    from nanoclaw.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanoclaw Status\n")

    console.print(
        f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}"
    )
    console.print(
        f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}"
    )

    if config_path.exists():
        from nanoclaw.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(
                    f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}"
                )


if __name__ == "__main__":
    app()
