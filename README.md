# Nanoclaw: Ultra-Lightweight Personal AI Assistant

<!-- markdownlint-disable MD013 MD036 MD060 -->

🦉 **nanoclaw** is an **ultra-lightweight** personal AI assistant built on top of [NHKUDS/nanobot](https://github.com/HKUDS/nanobot)

⚡️ Delivers core agent functionality in just **~4,500** lines of code — **99% smaller** than Clawdbot's 430k+ lines.

📏 Real-time line count: **4,520 lines** (run `bash core_agent_lines.sh` to verify anytime)

## Key Features of nanoclaw

🪶 **Ultra-Lightweight**: Just ~4,500 lines of core agent code — 99% smaller than Clawdbot.

🔬 **Research-Ready**: Clean, readable code that's easy to understand, modify, and extend for research.

⚡️ **Lightning Fast**: Minimal footprint means faster startup, lower resource usage, and quicker iterations.

💎 **Easy-to-Use**: One-click to deploy and you're ready to go.

## 🏗️ Architecture

![nanoclaw architecture](nanoclaw_arch.png)

## ✨ Features

| 📈 24/7 Real-Time Market Analysis | 🚀 Full-Stack Software Engineer | 📅 Smart Daily Routine Manager | 📚 Personal Knowledge Assistant |
|---|---|---|---|
| ![Market analysis demo](case/search.gif) | ![Coding demo](case/code.gif) | ![Schedule demo](case/scedule.gif) | ![Memory demo](case/memory.gif) |
| Discovery • Insights • Trends | Develop • Deploy • Scale | Schedule • Automate • Organize | Learn • Memory • Reasoning |

## 📦 Install

**Install from source** (latest features, recommended for development)

```bash
git clone https://github.com/luthebao/nanoclaw.git
cd nanoclaw
pip install -e .
```

**Install with [uv](https://github.com/astral-sh/uv)** (stable, fast)

```bash
uv tool install nanoclaw-ai
```

**Install from PyPI** (stable)

```bash
pip install nanoclaw-ai
```

## 🚀 Quick Start

> [!TIP]
> Set your API key in `~/.nanoclaw/config.json`.
> Get API keys: [OpenRouter](https://openrouter.ai/keys) (Global) · [Brave Search](https://brave.com/search/api/) (optional, for web search)

**1. Initialize**

```bash
nanoclaw onboard
```

**2. Configure** (`~/.nanoclaw/config.json`)

For OpenRouter - recommended for global users:

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  }
}
```

**3. Chat**

```bash
nanoclaw agent -m "What is 2+2?"
```

That's it! You have a working AI assistant in 2 minutes.

## 🖥️ Local Models (vLLM)

Run nanoclaw with your own local models using vLLM or any OpenAI-compatible server.

**1. Start your vLLM server**

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000
```

**2. Configure** (`~/.nanoclaw/config.json`)

```json
{
  "providers": {
    "vllm": {
      "apiKey": "dummy",
      "apiBase": "http://localhost:8000/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "meta-llama/Llama-3.1-8B-Instruct"
    }
  }
}
```

**3. Chat**

```bash
nanoclaw agent -m "Hello from my local LLM!"
```

> [!TIP]
> The `apiKey` can be any non-empty string for local servers that don't require authentication.

## 💬 Chat Apps

Talk to your nanoclaw through Telegram, Discord, WhatsApp, Feishu, Mochat, DingTalk, Slack, Email, or QQ — anytime, anywhere.

| Channel | Setup |
|---------|-------|
| **Telegram** | Easy (just a token) |
| **Discord** | Easy (bot token + intents) |
| **WhatsApp** | Medium (scan QR) |
| **Feishu** | Medium (app credentials) |
| **Mochat** | Medium (claw token + websocket) |
| **DingTalk** | Medium (app credentials) |
| **Slack** | Medium (bot + app tokens) |
| **Email** | Medium (IMAP/SMTP credentials) |
| **QQ** | Easy (app credentials) |

### Telegram (Recommended)

**1. Create a bot**

- Open Telegram, search `@BotFather`
- Send `/newbot`, follow prompts
- Copy the token

**2. Configure**

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

> You can find your **User ID** in Telegram settings. It is shown as `@yourUserId`.
> Copy this value **without the `@` symbol** and paste it into the config file.

**3. Run**

```bash
nanoclaw gateway
```

### Discord

**1. Create a bot**

- Go to [discord.com/developers/applications](https://discord.com/developers/applications)
- Create an application → Bot → Add Bot
- Copy the bot token

**2. Enable intents**

- In the Bot settings, enable **MESSAGE CONTENT INTENT**
- (Optional) Enable **SERVER MEMBERS INTENT** if you plan to use allow lists based on member data

**3. Get your User ID**

- Discord Settings → Advanced → enable **Developer Mode**
- Right-click your avatar → **Copy User ID**

**4. Configure**

```json
{
  "channels": {
    "discord": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

**5. Invite the bot**

- OAuth2 → URL Generator
- Scopes: `bot`
- Bot Permissions: `Send Messages`, `Read Message History`
- Open the generated invite URL and add the bot to your server

**6. Run**

```bash
nanoclaw gateway
```

### Email

Give nanoclaw its own email account. It polls **IMAP** for incoming mail and replies via **SMTP** — like a personal email assistant.

**1. Get credentials (Gmail example)**

- Create a dedicated Gmail account for your bot (e.g. `my-nanoclaw@gmail.com`)
- Enable 2-Step Verification → Create an [App Password](https://myaccount.google.com/apppasswords)
- Use this app password for both IMAP and SMTP

**2. Configure**

> - `consentGranted` must be `true` to allow mailbox access. This is a safety gate — set `false` to fully disable.
> - `allowFrom`: Leave empty to accept emails from anyone, or restrict to specific senders.
> - `smtpUseTls` and `smtpUseSsl` default to `true` / `false` respectively, which is correct for Gmail (port 587 + STARTTLS). No need to set them explicitly.
> - Set `"autoReplyEnabled": false` if you only want to read/analyze emails without sending automatic replies.

```json
{
  "channels": {
    "email": {
      "enabled": true,
      "consentGranted": true,
      "imapHost": "imap.gmail.com",
      "imapPort": 993,
      "imapUsername": "my-nanoclaw@gmail.com",
      "imapPassword": "your-app-password",
      "smtpHost": "smtp.gmail.com",
      "smtpPort": 587,
      "smtpUsername": "my-nanoclaw@gmail.com",
      "smtpPassword": "your-app-password",
      "fromAddress": "my-nanoclaw@gmail.com",
      "allowFrom": ["your-real-email@gmail.com"]
    }
  }
}
```

**3. Run**

```bash
nanoclaw gateway
```

## 🌐 Agent Social Network

🦉 nanoclaw is capable of linking to the agent social network (agent community). **Just send one message and your nanoclaw joins automatically!**

| Platform | How to Join (send this message to your bot) |
|----------|-------------|
| [**Moltbook**](https://www.moltbook.com/) | `Read https://moltbook.com/skill.md and follow the instructions to join Moltbook` |
| [**ClawdChat**](https://clawdchat.ai/) | `Read https://clawdchat.ai/skill.md and follow the instructions to join ClawdChat` |

Simply send the command above to your nanoclaw (via CLI or any chat channel), and it will handle the rest.

## ⚙️ Configuration

Config file: `~/.nanoclaw/config.json`

### Providers

> [!TIP]
>
> - **Groq** provides free voice transcription via Whisper. If configured, Telegram voice messages will be automatically transcribed.
> - **Zhipu Coding Plan**: If you're on Zhipu's coding plan, set `"apiBase": "https://open.bigmodel.cn/api/coding/paas/v4"` in your zhipu provider config.
> - **MiniMax (Mainland China)**: If your API key is from MiniMax's mainland China platform (minimaxi.com), set `"apiBase": "https://api.minimaxi.com/v1"` in your minimax provider config.

| Provider | Purpose | Get API Key |
|----------|---------|-------------|
| `openrouter` | LLM (recommended, access to all models) | [openrouter.ai](https://openrouter.ai) |
| `anthropic` | LLM (Claude direct) | [console.anthropic.com](https://console.anthropic.com) |
| `openai` | LLM (GPT direct) | [platform.openai.com](https://platform.openai.com) |
| `deepseek` | LLM (DeepSeek direct) | [platform.deepseek.com](https://platform.deepseek.com) |
| `groq` | LLM + **Voice transcription** (Whisper) | [console.groq.com](https://console.groq.com) |
| `gemini` | LLM (Gemini direct) | [aistudio.google.com](https://aistudio.google.com) |
| `minimax` | LLM (MiniMax direct) | [platform.minimax.io](https://platform.minimax.io) |
| `aihubmix` | LLM (API gateway, access to all models) | [aihubmix.com](https://aihubmix.com) |
| `dashscope` | LLM (Qwen) | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com) |
| `moonshot` | LLM (Moonshot/Kimi) | [platform.moonshot.cn](https://platform.moonshot.cn) |
| `zhipu` | LLM (Zhipu GLM) | [open.bigmodel.cn](https://open.bigmodel.cn) |
| `vllm` | LLM (local, any OpenAI-compatible server) | — |

### Adding a New Provider (Developer Guide)

nanoclaw uses a **Provider Registry** (`nanoclaw/providers/registry.py`) as the single source of truth.
Adding a new provider only takes **2 steps** — no if-elif chains to touch.

**Step 1.** Add a `ProviderSpec` entry to `PROVIDERS` in `nanoclaw/providers/registry.py`:

```python
ProviderSpec(
    name="myprovider",                   # config field name
    keywords=("myprovider", "mymodel"),  # model-name keywords for auto-matching
    env_key="MYPROVIDER_API_KEY",        # env var for LiteLLM
    display_name="My Provider",          # shown in `nanoclaw status`
    litellm_prefix="myprovider",         # auto-prefix: model → myprovider/model
    skip_prefixes=("myprovider/",),      # don't double-prefix
)
```

**Step 2.** Add a field to `ProvidersConfig` in `nanoclaw/config/schema.py`:

```python
class ProvidersConfig(BaseModel):
    ...
    myprovider: ProviderConfig = ProviderConfig()
```

That's it! Environment variables, model prefixing, config matching, and `nanoclaw status` display will all work automatically.

**Common `ProviderSpec` options:**

| Field | Description | Example |
|-------|-------------|---------|
| `litellm_prefix` | Auto-prefix model names for LiteLLM | `"dashscope"` → `dashscope/qwen-max` |
| `skip_prefixes` | Don't prefix if model already starts with these | `("dashscope/", "openrouter/")` |
| `env_extras` | Additional env vars to set | `(("ZHIPUAI_API_KEY", "{api_key}"),)` |
| `model_overrides` | Per-model parameter overrides | `(("kimi-k2.5", {"temperature": 1.0}),)` |
| `is_gateway` | Can route any model (like OpenRouter) | `True` |
| `detect_by_key_prefix` | Detect gateway by API key prefix | `"sk-or-"` |
| `detect_by_base_keyword` | Detect gateway by API base URL | `"openrouter"` |
| `strip_model_prefix` | Strip existing prefix before re-prefixing | `True` (for AiHubMix) |

### Security

> For production deployments, set `"restrictToWorkspace": true` in your config to sandbox the agent.

| Option | Default | Description |
|--------|---------|-------------|
| `tools.restrictToWorkspace` | `false` | When `true`, restricts **all** agent tools (shell, file read/write/edit, list) to the workspace directory. Prevents path traversal and out-of-scope access. |
| `channels.*.allowFrom` | `[]` (allow all) | Whitelist of user IDs. Empty = allow everyone; non-empty = only listed users can interact. |

## CLI Reference

| Command | Description |
|---------|-------------|
| `nanoclaw --version` | Show version |
| `nanoclaw onboard` | Initialize config & workspace |
| `nanoclaw status` | Show status |

### Agent

| Command | Description |
|---------|-------------|
| `nanoclaw agent` | Interactive chat mode |
| `nanoclaw agent -m "..."` | Send a single message |
| `nanoclaw agent -s SESSION_ID` | Use a specific session |
| `nanoclaw agent --no-markdown` | Show plain-text replies |
| `nanoclaw agent --logs` | Show runtime logs during chat |
| `nanoclaw agent serve` | Run agent as TCP server (foreground) |

Interactive mode exits: `exit`, `quit`, `/exit`, `/quit`, `:q`, or `Ctrl+D`.

### Gateway

| Command | Description |
|---------|-------------|
| `nanoclaw gateway` | Start the gateway (foreground) |
| `nanoclaw gateway run` | Run the gateway in the foreground (used by daemon) |
| `nanoclaw gateway install` | Install gateway as OS daemon |
| `nanoclaw gateway uninstall` | Remove the gateway OS service |
| `nanoclaw gateway start` | Start the gateway daemon |
| `nanoclaw gateway stop` | Stop the gateway daemon |
| `nanoclaw gateway restart` | Restart the gateway daemon |
| `nanoclaw gateway status` | Show gateway daemon status |
| `nanoclaw gateway logs` | Tail gateway logs |
| `nanoclaw gateway logs -f` | Follow gateway log output |
| `nanoclaw gateway logs -e` | Show stderr log instead |

### Channels

| Command | Description |
|---------|-------------|
| `nanoclaw channels status` | Show channel status |
| `nanoclaw channels login` | Link device via QR code |

### Scheduled Tasks (Cron)

| Command | Description |
|---------|-------------|
| `nanoclaw cron list` | List scheduled jobs |
| `nanoclaw cron list -a` | Include disabled jobs |
| `nanoclaw cron add --name "daily" --message "Good morning!" --cron "0 9 * * *"` | Add a cron job |
| `nanoclaw cron add --name "hourly" --message "Check status" --every 3600` | Add an interval job |
| `nanoclaw cron remove JOB_ID` | Remove a scheduled job |
| `nanoclaw cron enable JOB_ID` | Enable a job |
| `nanoclaw cron enable JOB_ID --disable` | Disable a job |
| `nanoclaw cron run JOB_ID` | Manually run a job |

## 🖥️ Background Daemons (macOS / Linux)

nanoclaw supports running the **gateway** as an OS background daemon. Optionally, the agent can run as a separate foreground process connected via TCP.

```
  Gateway Process                    Agent Process (optional)
┌─────────────────────┐         ┌─────────────────────┐
│ ChannelManager      │         │ AgentLoop           │
│ CronService         │  TCP    │ LLMProvider         │
│ HeartbeatService    │◄───────►│ SessionManager      │
│ NetworkBus (client) │ :18791  │ NetworkBus (server)  │
└─────────────────────┘         └─────────────────────┘
```

When the agent is not running separately, `nanoclaw gateway` falls back to in-process mode (all-in-one, same as before).

> [!IMPORTANT]
> On macOS, launchd cannot access virtualenv paths due to sandbox restrictions.
> You **must** install nanoclaw globally before setting up the gateway daemon.

**1. Install nanoclaw globally**

```bash
# From the project directory
uv tool install .

# Or from PyPI
uv tool install nanoclaw-ai
```

To update after making changes to the codebase:

```bash
uv tool install . --force
```

**2. Install and start the gateway daemon**

```bash
nanoclaw gateway install
nanoclaw gateway start
```

**Gateway daemon management:**

```bash
nanoclaw gateway stop      # Stop the gateway daemon
nanoclaw gateway restart   # Restart the gateway daemon
nanoclaw gateway status    # Show gateway daemon status
nanoclaw gateway logs -f   # Follow gateway logs
nanoclaw gateway uninstall # Remove the gateway service
```

**Running the agent separately (advanced):**

For production setups where you want the agent to persist across gateway restarts, run the agent as a foreground TCP server and manage its lifecycle yourself (e.g. via tmux, screen, or systemd):

```bash
nanoclaw agent serve       # Run agent as TCP server (foreground)
```

> [!TIP]
> You can run `nanoclaw gateway` without a separate agent process — it will use in-process mode automatically. The split-process setup is optional.

> [!NOTE]
> If you run `nanoclaw gateway install` from inside a virtualenv (e.g. via `uv run`), it will fail with an error and instructions to install globally first.

## 🐳 Docker

> [!TIP]
> The `-v ~/.nanoclaw:/root/.nanoclaw` flag mounts your local config directory into the container, so your config and workspace persist across container restarts.

Build and run nanoclaw in a container:

```bash
# Build the image
docker build -t nanoclaw .

# Initialize config (first time only)
docker run -v ~/.nanoclaw:/root/.nanoclaw --rm nanoclaw onboard

# Edit config on host to add API keys
vim ~/.nanoclaw/config.json

# Run gateway (connects to enabled channels, e.g. Telegram/Discord/Mochat)
docker run -v ~/.nanoclaw:/root/.nanoclaw -p 18790:18790 nanoclaw gateway

# Or run a single command
docker run -v ~/.nanoclaw:/root/.nanoclaw --rm nanoclaw agent -m "Hello!"
docker run -v ~/.nanoclaw:/root/.nanoclaw --rm nanoclaw status
```

## 📁 Project Structure

```sh
nanoclaw/
├── agent/          # 🧠 Core agent logic
│   ├── loop.py     #    Agent loop (LLM ↔ tool execution)
│   ├── context.py  #    Prompt builder
│   ├── memory.py   #    Persistent memory
│   ├── skills.py   #    Skills loader
│   ├── subagent.py #    Background task execution
│   └── tools/      #    Built-in tools (incl. spawn)
├── skills/         # 🎯 Bundled skills (github, weather, tmux...)
├── channels/       # 📱 Chat channel integrations
├── bus/            # 🚌 Message routing (in-process + TCP network bus)
├── cron/           # ⏰ Scheduled tasks
├── heartbeat/      # 💓 Proactive wake-up
├── providers/      # 🤖 LLM providers (OpenRouter, etc.)
├── session/        # 💬 Conversation sessions
├── config/         # ⚙️ Configuration
└── cli/            # 🖥️ Commands
```

nanoclaw is for educational, research, and technical exchange purposes only.
