"""TCP-based message bus for split agent/gateway processes."""

import asyncio
import json
import struct
from typing import Awaitable, Callable

from loguru import logger

from nanoclaw.bus.events import InboundMessage, OutboundMessage

_HEADER_FMT = "!I"  # 4-byte big-endian unsigned int
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


# ------------------------------------------------------------------
# Wire helpers
# ------------------------------------------------------------------


async def _send_msg(writer: asyncio.StreamWriter, payload: dict) -> None:
    """Send a length-prefixed JSON message."""
    data = json.dumps(payload).encode()
    writer.write(struct.pack(_HEADER_FMT, len(data)) + data)
    await writer.drain()


async def _recv_msg(reader: asyncio.StreamReader) -> dict | None:
    """Read a length-prefixed JSON message. Returns None on EOF."""
    header = await reader.readexactly(_HEADER_SIZE)
    (length,) = struct.unpack(_HEADER_FMT, header)
    data = await reader.readexactly(length)
    return json.loads(data)


# ------------------------------------------------------------------
# Server (agent side)
# ------------------------------------------------------------------


class NetworkBusServer:
    """Agent-side TCP bus server.

    Accepts connections from the gateway, receives inbound messages,
    and sends outbound messages back.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 18791):
        self.host = host
        self.port = port
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._clients: list[asyncio.StreamWriter] = []
        self._server: asyncio.Server | None = None
        self._running = False

    # -- MessageBus-compatible interface --------------------------------

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await self._inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        return await self._inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        payload = {"type": "outbound", "data": msg.to_dict()}
        dead: list[asyncio.StreamWriter] = []
        for writer in self._clients:
            try:
                await _send_msg(writer, payload)
            except (ConnectionError, OSError):
                dead.append(writer)
        for w in dead:
            self._clients.remove(w)

    # -- TCP server -----------------------------------------------------

    async def serve(self) -> None:
        self._running = True
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logger.info(f"NetworkBusServer listening on {self.host}:{self.port}")
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info(f"Gateway connected from {addr}")
        self._clients.append(writer)
        try:
            while self._running:
                try:
                    msg = await _recv_msg(reader)
                except (asyncio.IncompleteReadError, ConnectionError, OSError):
                    break
                if msg is None:
                    break
                if msg.get("type") == "inbound":
                    inbound = InboundMessage.from_dict(msg["data"])
                    await self._inbound.put(inbound)
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            writer.close()
            logger.info(f"Gateway disconnected: {addr}")

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()

    @property
    def inbound_size(self) -> int:
        return self._inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return 0  # outbound is sent immediately to clients


# ------------------------------------------------------------------
# Client (gateway side)
# ------------------------------------------------------------------


class NetworkBusClient:
    """Gateway-side TCP bus client.

    Connects to the agent's TCP server, sends inbound messages,
    and receives outbound messages for dispatch.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 18791):
        self.host = host
        self.port = port
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers: dict[
            str, list[Callable[[OutboundMessage], Awaitable[None]]]
        ] = {}
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False
        self._recv_task: asyncio.Task | None = None

    # -- Connection -----------------------------------------------------

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._running = True
        self._recv_task = asyncio.create_task(self._receive_loop())
        logger.info(f"Connected to agent at {self.host}:{self.port}")

    async def _receive_loop(self) -> None:
        """Continuously read outbound messages from the agent."""
        assert self._reader is not None
        while self._running:
            try:
                msg = await _recv_msg(self._reader)
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                logger.warning("Lost connection to agent")
                break
            if msg is None:
                break
            if msg.get("type") == "outbound":
                outbound = OutboundMessage.from_dict(msg["data"])
                await self._outbound.put(outbound)

    # -- MessageBus-compatible interface --------------------------------

    async def publish_inbound(self, msg: InboundMessage) -> None:
        if self._writer is None:
            raise ConnectionError("Not connected to agent")
        payload = {"type": "inbound", "data": msg.to_dict()}
        await _send_msg(self._writer, payload)

    async def consume_outbound(self) -> OutboundMessage:
        return await self._outbound.get()

    def subscribe_outbound(
        self, channel: str, callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self._outbound.get(), timeout=1.0)
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._running = False
        if self._recv_task:
            self._recv_task.cancel()
        if self._writer:
            self._writer.close()

    @property
    def inbound_size(self) -> int:
        return 0  # inbound is sent immediately to server

    @property
    def outbound_size(self) -> int:
        return self._outbound.qsize()
