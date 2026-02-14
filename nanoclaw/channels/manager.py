"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanoclaw.bus.queue import MessageBus
from nanoclaw.channels.base import BaseChannel
from nanoclaw.config.schema import Config

if TYPE_CHECKING:
    from nanoclaw.bus.network import NetworkBusClient
    from nanoclaw.session.manager import SessionManager


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(
        self,
        config: Config,
        bus: "MessageBus | NetworkBusClient",
        session_manager: "SessionManager | None" = None,
    ):
        self.config = config
        self.bus = bus
        self.session_manager = session_manager
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None

        self._init_channels()

    def _init_channels(self) -> None:
        """Initialize channels based on config."""
        import importlib

        # (name, module_path, class_name, extra_kwargs_factory or None)
        channel_registry: list[tuple[str, str, str, dict[str, Any] | None]] = [
            (
                "telegram",
                "nanoclaw.channels.telegram",
                "TelegramChannel",
                {
                    "groq_api_key": self.config.providers.groq.api_key,
                    "session_manager": self.session_manager,
                },
            ),
            ("discord", "nanoclaw.channels.discord", "DiscordChannel", None),
            ("email", "nanoclaw.channels.email", "EmailChannel", None),
        ]

        for name, module_path, class_name, extra_kwargs in channel_registry:
            ch_config = getattr(self.config.channels, name)
            if not ch_config.enabled:
                continue
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                kwargs: dict[str, Any] = {}
                if extra_kwargs:
                    kwargs.update(extra_kwargs)
                self.channels[name] = cls(ch_config, self.bus, **kwargs)
                logger.info(f"{name.capitalize()} channel enabled")
            except ImportError as e:
                logger.warning(f"{name.capitalize()} channel not available: {e}")

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel with retries on failure."""
        max_retries = 5
        delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                await channel.start()
                return
            except Exception as e:
                if attempt == max_retries:
                    logger.error(
                        f"Failed to start channel {name} after {max_retries} attempts: {e}"
                    )
                    return
                logger.warning(
                    f"Failed to start channel {name} (attempt {attempt}/{max_retries}): "
                    f"{e}, retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        if not self.channels:
            logger.warning("No channels enabled")
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info(f"Starting {name} channel...")
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")

        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")

        while True:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)

                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error(f"Error sending to {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {"enabled": True, "running": channel.is_running}
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
