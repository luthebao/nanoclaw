"""Message bus module for decoupled channel-agent communication."""

from nanoclaw.bus.events import InboundMessage, OutboundMessage
from nanoclaw.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
