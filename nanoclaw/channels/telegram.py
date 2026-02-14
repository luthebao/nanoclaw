"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from loguru import logger
from telegram import (
    BotCommand,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from nanoclaw.bus.events import OutboundMessage
from nanoclaw.bus.queue import MessageBus
from nanoclaw.channels.base import BaseChannel
from nanoclaw.config.schema import TelegramConfig

if TYPE_CHECKING:
    from nanoclaw.session.manager import SessionManager


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []

    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []

    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)

    # 3. Headers # Title -> just the title text
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)

    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # 7. Bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 10. Bullet lists - item -> • item
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


TELEGRAM_MAX_LENGTH = 4096


def _split_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """
    Split a message into chunks that fit within Telegram's character limit.

    Splits at natural boundaries in priority order:
    1. Double newline (paragraph break)
    2. Single newline
    3. Space
    4. Hard cut at max_length
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Try splitting at natural boundaries (search backwards from the limit)
        split_at = -1
        for sep in ("\n\n", "\n", " "):
            pos = text.rfind(sep, 0, max_length)
            if pos > 0:
                split_at = pos
                break

        if split_at <= 0:
            # Hard cut as last resort
            split_at = max_length

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")  # strip leading newlines from next chunk

    return chunks


def _detect_choice_buttons(text: str) -> list[dict[str, str]] | None:
    """
    Detect multiple-choice or yes-no patterns and return button definitions.

    Detects patterns like:
    - Letter choices: A) Red, **B.** Blue, C: Green, D] Purple
    - Numbered choices: 1. Option one, 2) Option two
    - Yes/No patterns: "yes/no", "type yes or no"
    - Prompt patterns: "type A/B/C/D to proceed", "multiple choice", "choose one:"
    """
    # Pattern 1: Letter choices (A) Red, **B.** Blue, C: Green, D] Purple)
    letter_pattern = re.compile(r"^\s*\*{0,2}([A-D])[).:\]]\*{0,2}\s+(.+)$", re.MULTILINE)
    matches = letter_pattern.findall(text)
    if len(matches) >= 2:
        buttons = []
        for letter, label_text in matches:
            # Strip markdown bold/italic
            label_text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", label_text)
            label_text = re.sub(r"_(.+?)_", r"\1", label_text)
            label = f"{letter}) {label_text.strip()}"
            if len(label) > 40:
                label = label[:37] + "..."
            buttons.append({"label": label, "data": letter})
        if len(buttons) > 8:
            return None
        return buttons

    # Pattern 2: Numbered choices (1. Option, 2) Option, 3: Option)
    number_pattern = re.compile(r"^\s*\*{0,2}(\d+)[).:\]]\*{0,2}\s+(.+)$", re.MULTILINE)
    num_matches = number_pattern.findall(text)
    if len(num_matches) >= 2 and len(num_matches) <= 8:
        buttons = []
        for num, label_text in num_matches:
            label_text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", label_text)
            label_text = re.sub(r"_(.+?)_", r"\1", label_text)
            label = f"{num}) {label_text.strip()}"
            if len(label) > 40:
                label = label[:37] + "..."
            buttons.append({"label": label, "data": num})
        return buttons

    # Pattern 3: Yes/No patterns
    yesno_pattern = re.compile(
        r"(?:yes\s*/\s*no|yes\s+or\s+no|type\s+(?:yes|no)|confirm\s*\?)",
        re.IGNORECASE,
    )
    if yesno_pattern.search(text):
        return [
            {"label": "Yes", "data": "Yes"},
            {"label": "No", "data": "No"},
        ]

    # Pattern 4: "type A/B/C/D to proceed" style prompts
    type_letter_pattern = re.compile(
        r"type\s+([A-D])\s*(?:/|or|\s)\s*([A-D])(?:\s*(?:/|or|\s)\s*([A-D]))?(?:\s*(?:/|or|\s)\s*([A-D]))?\s*(?:to\s+proceed|to\s+continue|to\s+select)?",
        re.IGNORECASE,
    )
    type_match = type_letter_pattern.search(text)
    if type_match:
        letters = [g.upper() for g in type_match.groups() if g]
        if len(letters) >= 2:
            return [{"label": letter, "data": letter} for letter in letters]

    # Pattern 5: "choose one:" followed by inline options like "A - Option1, B - Option2"
    choose_pattern = re.compile(r"choose\s+(?:one\s*)?:\s*(.+)", re.IGNORECASE)
    choose_match = choose_pattern.search(text)
    if choose_match:
        options_text = choose_match.group(1)
        # Try to parse "A - Option1, B - Option2" or "A: Option1 | B: Option2"
        inline_options = re.findall(
            r"\b([A-D])\s*[-:|]\s*([^,|]+?)(?:\s*[,|]|\s*$)",
            options_text,
            re.IGNORECASE,
        )
        if len(inline_options) >= 2:
            buttons = []
            for letter, label_text in inline_options:
                label_text = label_text.strip()
                if len(label_text) > 30:
                    label_text = label_text[:27] + "..."
                buttons.append({"label": f"{letter}) {label_text}", "data": letter.upper()})
            return buttons

    return None


def _build_reply_keyboard(buttons: list[dict[str, str]]) -> ReplyKeyboardMarkup:
    """Build a ReplyKeyboardMarkup from button definitions. Each button on its own row."""
    # Each button on its own row, sends its label as text when tapped
    rows = [[KeyboardButton(text=b["label"])] for b in buttons]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,  # Auto-size buttons
        one_time_keyboard=True,  # Hide after tap
    )


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.


    Simple and reliable - no webhook/public IP needed.
    """

    name = "telegram"

    # Commands registered with Telegram's command menu
    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("reset", "Reset conversation history"),
        BotCommand("allow", "Add your user ID to allow_from"),
        BotCommand("help", "Show available commands"),
    ]

    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
        session_manager: SessionManager | None = None,
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self.session_manager = session_manager
        self._app: Application | None = None
        self._bot_username: str | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        self._running = True

        # Build the application with larger connection pool to avoid pool-timeout on long runs
        req = HTTPXRequest(
            connection_pool_size=16,
            pool_timeout=5.0,
            connect_timeout=30.0,
            read_timeout=30.0,
        )
        builder = (
            Application.builder().token(self.config.token).request(req).get_updates_request(req)
        )
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("reset", self._on_reset))
        self._app.add_handler(CommandHandler("allow", self._on_allow))
        self._app.add_handler(CommandHandler("help", self._on_help))

        # Add message handler for text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (
                    filters.TEXT
                    | filters.PHOTO
                    | filters.VOICE
                    | filters.AUDIO
                    | filters.Document.ALL
                )
                & ~filters.COMMAND,
                self._on_message,
            )
        )

        # Add callback query handler for inline keyboard buttons
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))

        logger.info("Starting Telegram bot (polling mode)...")

        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()

        # Get bot info and register command menu
        bot_info = await self._app.bot.get_me()
        self._bot_username = bot_info.username
        logger.info(f"Telegram bot @{bot_info.username} connected")

        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as e:
            logger.warning(f"Failed to register bot commands: {e}")

        # Start polling (this runs until stopped)
        assert self._app.updater is not None
        await self._app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,  # Ignore old messages on startup
        )

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False

        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        if self._app:
            logger.info("Stopping Telegram bot...")
            assert self._app.updater is not None
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return

        # Stop typing indicator for this chat
        self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
            return

        # Detect reply keyboard buttons from the full message
        detected = _detect_choice_buttons(msg.content)
        keyboard = _build_reply_keyboard(detected) if detected else None

        # Split markdown first, then convert each chunk to HTML individually.
        # This avoids breaking HTML tags mid-element.
        md_chunks = _split_message(msg.content)

        for i, chunk in enumerate(md_chunks):
            is_last = i == len(md_chunks) - 1
            # On the last chunk: show keyboard if buttons detected, otherwise remove any existing keyboard
            if is_last:
                markup = keyboard if keyboard else ReplyKeyboardRemove()
            else:
                markup = None
            try:
                html_content = _markdown_to_telegram_html(chunk)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=html_content,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            except Exception as e:
                logger.warning(f"HTML parse failed for chunk {i}, falling back to plain text: {e}")
                try:
                    # Plain text fallback — also needs splitting
                    plain_chunks = _split_message(chunk)
                    for j, plain_chunk in enumerate(plain_chunks):
                        plain_is_last = is_last and j == len(plain_chunks) - 1
                        await self._app.bot.send_message(
                            chat_id=chat_id,
                            text=plain_chunk,
                            reply_markup=markup if plain_is_last else None,
                        )
                        if len(plain_chunks) > 1:
                            await asyncio.sleep(0.05)
                except Exception as e2:
                    logger.error(f"Error sending Telegram message: {e2}")

            if len(md_chunks) > 1 and i < len(md_chunks) - 1:
                await asyncio.sleep(0.05)

    def _check_command_allowed(self, update: Update) -> bool:
        """Return True if the command sender is allowed."""
        if not update.message or not update.effective_user:
            return False
        user = update.effective_user
        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"
        chat_id = str(update.message.chat_id)
        return self.is_allowed(sender_id, chat_id)

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return
        if not self._check_command_allowed(update):
            return

        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm nanoclaw.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command — clear conversation history."""
        if not update.message or not update.effective_user:
            return
        if not self._check_command_allowed(update):
            return

        chat_id = str(update.message.chat_id)
        session_key = f"{self.name}:{chat_id}"

        if self.session_manager is None:
            logger.warning("/reset called but session_manager is not available")
            await update.message.reply_text("⚠️ Session management is not available.")
            return

        session = self.session_manager.get_or_create(session_key)
        msg_count = len(session.messages)
        session.clear()
        self.session_manager.save(session)

        # Clear gateway log files
        from nanoclaw.utils.helpers import get_data_path

        log_dir = get_data_path() / "logs"
        for log_name in ("gateway.out.log", "gateway.err.log"):
            log_file = log_dir / log_name
            try:
                log_file.open("w").close()
            except OSError:
                logger.debug(f"Could not clear {log_file}")

        logger.info(f"Session reset for {session_key} (cleared {msg_count} messages, logs cleared)")
        await update.message.reply_text(
            "🔄 Conversation history and gateway logs cleared. Let's start fresh!"
        )

    async def _on_allow(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /allow command — add user ID to allow_from list."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        user_id = str(user.id)

        # Check if already allowed
        if self.is_allowed(user_id, str(update.message.chat_id)):
            await update.message.reply_text(f"✅ You are already allowed (ID: `{user_id}`)")
            return

        # Add user ID to config
        from nanoclaw.config.loader import load_config, save_config

        config = load_config()
        if user_id not in config.channels.telegram.allow_from:
            config.channels.telegram.allow_from.append(user_id)
            save_config(config)
            logger.info(f"Added user {user_id} to telegram allow_from")
            await update.message.reply_text(
                f"✅ Added your user ID to allow_from:\n`{user_id}`\n\nYou can now use the bot!"
            )
        else:
            await update.message.reply_text(f"✅ Your user ID `{user_id}` is already in allow_from")

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command — show available commands."""
        if not update.message:
            return
        if not self._check_command_allowed(update):
            return

        help_text = (
            "🐈 <b>nanoclaw commands</b>\n\n"
            "/start — Start the bot\n"
            "/reset — Reset conversation history\n"
            "/help — Show this help message\n\n"
            "Just send me a text message to chat!"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")

    def _is_mentioned(self, message) -> bool:
        """Check if the bot is @mentioned in a message."""
        if not self._bot_username:
            return False
        bot_tag = f"@{self._bot_username.lower()}"
        # Check entities for mention targeting this bot
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    text = message.text[entity.offset : entity.offset + entity.length]
                    if text.lower() == bot_tag:
                        return True
        # Fallback: check raw text
        if message.text and bot_tag in message.text.lower():
            return True
        return False

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id

        # Use stable numeric ID, but keep username for allowlist compatibility
        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"

        # In groups: require @mention AND chat_id in allow_from
        if message.chat.type != "private":
            if not self._is_mentioned(message):
                return
            if not self.is_allowed(sender_id, str(chat_id)):
                logger.debug(f"Group {chat_id} not in allow_from, ignoring")
                return
        else:
            # Private chats: check sender is allowed before any processing
            if not self.is_allowed(sender_id, str(chat_id)):
                logger.debug(f"Sender {sender_id} not in allow_from, ignoring DM")
                return

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id

        # Build content from text and/or media
        content_parts = []
        media_paths = []

        # Text content (strip @botname from group messages)
        if message.text:
            text = message.text
            if self._bot_username:
                text = re.sub(
                    rf"@{re.escape(self._bot_username)}\s*",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
            if text:
                content_parts.append(text)
        if message.caption:
            content_parts.append(message.caption)

        # Handle media files
        media_file = None
        media_type = None

        if message.photo:
            media_file = message.photo[-1]  # Largest photo
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"

        # Download media if present
        if media_file and media_type and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                ext = self._get_extension(media_type, getattr(media_file, "mime_type", None))

                # Save to workspace/media/
                from nanoclaw.utils.helpers import get_data_path

                media_dir = get_data_path() / "media"
                media_dir.mkdir(parents=True, exist_ok=True)

                file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
                await file.download_to_drive(str(file_path))

                media_paths.append(str(file_path))

                # Handle voice transcription
                if media_type == "voice" or media_type == "audio":
                    from nanoclaw.providers.transcription import (
                        GroqTranscriptionProvider,
                    )

                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info(f"Transcribed {media_type}: {transcription[:50]}...")
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")

                logger.debug(f"Downloaded {media_type} to {file_path}")
            except Exception as e:
                logger.error(f"Failed to download media: {e}")
                content_parts.append(f"[{media_type}: download failed]")

        content = "\n".join(content_parts) if content_parts else "[empty message]"

        logger.debug(f"Telegram message from {sender_id}: {content[:50]}...")

        str_chat_id = str(chat_id)

        # Start typing indicator before processing
        self._start_typing(str_chat_id)

        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private",
            },
        )

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard button presses."""
        query = update.callback_query
        if not query or not query.from_user:
            return

        user = query.from_user
        message = query.message
        if not isinstance(message, Message):
            return

        chat_id = str(message.chat_id)

        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"

        if not self.is_allowed(sender_id, chat_id):
            logger.debug(f"Callback query from {sender_id} not allowed, ignoring")
            return

        # Acknowledge the button press (removes loading spinner)
        await query.answer()

        button_data = query.data or ""

        # Edit original message: append selection and remove keyboard
        try:
            original_text = message.text_html or message.text or ""
            edited = f"{original_text}\n\n✓ {button_data}"
            await message.edit_text(text=edited, parse_mode="HTML", reply_markup=None)
        except Exception as e:
            logger.debug(f"Could not edit message after button press: {e}")

        # Start typing indicator
        self._start_typing(chat_id)

        # Forward the button choice to the agent as if the user typed it
        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=button_data,
            metadata={
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "from_button": True,
            },
        )

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                try:
                    await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"Typing indicator error for {chat_id}: {e}")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors instead of silently swallowing them."""
        logger.error(f"Telegram error: {context.error}")

    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")
