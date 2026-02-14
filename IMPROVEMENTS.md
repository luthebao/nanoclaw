# nanoclaw Improvement Opportunities

Analysis date: 2026-02-14
Based on: Deep codebase analysis + nanobot upstream comparison

---

## 🔴 High Priority (Missing Features from nanobot)

### 1. `last_consolidated` Session Tracking
**File:** `nanoclaw/session/manager.py`

**Problem:** nanoclaw re-consolidates the same messages repeatedly. nanobot tracks `last_consolidated` to avoid redundant LLM calls.

**Current:**
```python
@dataclass
class Session:
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    # ... missing last_consolidated
```

**Fix:** Add field and use in `_consolidate_memory()`:
```python
last_consolidated: int = 0  # Number of messages already consolidated
```

**Impact:** Reduces memory consolidation API calls by ~50-80%

---

### 2. Slash Commands (`/new`, `/help`)
**File:** `nanoclaw/agent/loop.py`

**Problem:** Users can't reset sessions or get help without the agent interpreting it as a regular message.

**Add to `_process_message()`:**
```python
cmd = msg.content.strip().lower()
if cmd == "/new":
    # Archive current session and start fresh
    messages_to_archive = session.messages.copy()
    session.clear()
    self.sessions.save(session)
    self.sessions.invalidate(session.key)
    asyncio.create_task(self._consolidate_memory(session, archive_all=True))
    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                          content="New session started. 🦉")
if cmd == "/help":
    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                          content="🦉 nanoclaw commands:\n/new — Start a new conversation\n/help — Show available commands")
```

**Impact:** Better UX, especially on chat platforms

---

### 3. Refactor: Extract `_run_agent_loop()` Helper
**File:** `nanoclaw/agent/loop.py`

**Problem:** `_process_message()` and `_process_system_message()` have ~60 lines of duplicated agent loop code.

**Solution:** Extract to a helper method (as nanobot does):
```python
async def _run_agent_loop(self, initial_messages: list[dict]) -> tuple[str | None, list[str]]:
    """Run the agent iteration loop. Returns (final_content, tools_used)."""
    messages = initial_messages
    iteration = 0
    final_content = None
    tools_used: list[str] = []

    while iteration < self.max_iterations:
        iteration += 1
        response = await self.provider.chat(
            messages=messages,
            tools=self.tools.get_definitions(),
            model=self.model,
        )
        # ... handle tool calls or return
    return final_content, tools_used
```

**Impact:** ~60 lines of code reduction, easier maintenance

---

### 4. Refactor: Extract `_update_tool_contexts()` Helper
**File:** `nanoclaw/agent/loop.py`

**Already exists in nanoclaw!** ✅ (Named `_update_tool_contexts`)

---

## 🟡 Medium Priority (Code Quality)

### 5. Add `reasoning_content` to Assistant Messages
**File:** `nanoclaw/agent/context.py`

**Problem:** Thinking models (DeepSeek-R1, Kimi) return `reasoning_content` that must be preserved in history.

**Current:** Already implemented in `add_assistant_message()` ✅

**But not used in loop.py!** Fix:
```python
messages = self.context.add_assistant_message(
    messages, response.content, tool_call_dicts,
    reasoning_content=response.reasoning_content,  # Add this
)
```

---

### 6. LRU Cache Eviction for Sessions
**File:** `nanoclaw/session/manager.py`

**Status:** Already implemented ✅ (nanoclaw has `_evict_if_needed()` with OrderedDict)

**nanobot doesn't have this!** nanoclaw is ahead here.

---

### 7. File Caching in ContextBuilder
**File:** `nanoclaw/agent/context.py`

**Status:** Already implemented ✅ (`_read_cached()` with mtime-based caching)

**nanobot doesn't have this!** nanoclaw is ahead here.

---

## 🟢 Low Priority (Nice to Have)

### 8. Context Window Auto-Compaction
**File:** `nanoclaw/agent/loop.py`

**Status:** Already implemented ✅ (`_maybe_compact()` with `context_window` and `compaction_threshold`)

**nanobot doesn't have this!** nanoclaw is ahead here.

---

### 9. Subagent Concurrency Limit
**File:** `nanoclaw/agent/subagent.py`

**Status:** Already implemented ✅ (`max_concurrent` + `_reap_done_tasks()`)

**nanobot doesn't have this!** nanoclaw is ahead here.

---

### 10. Streaming Responses
**Files:** `providers/`, `agent/loop.py`

**Idea:** Stream LLM responses to users in real-time instead of waiting for complete response.

**Implementation:**
- Add `stream=True` parameter to provider
- Use `yield` or asyncio queues
- Update channels to support streaming

**Impact:** Better UX for long responses

---

### 11. Tool Output Truncation
**File:** `nanoclaw/agent/tools/shell.py`

**Idea:** Truncate large tool outputs before sending to LLM (save tokens).

```python
MAX_TOOL_OUTPUT = 10000
if len(result) > MAX_TOOL_OUTPUT:
    result = result[:MAX_TOOL_OUTPUT] + "\n...[truncated]"
```

**Impact:** Prevent context overflow from verbose commands

---

### 12. Retry Logic for LLM Calls
**File:** `nanoclaw/agent/loop.py`

**Idea:** Add exponential backoff for transient API failures.

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def _call_llm(self, messages, tools):
    return await self.provider.chat(messages=messages, tools=tools, model=self.model)
```

**Impact:** More resilient to API hiccups

---

### 13. Structured Logging with Trace IDs
**File:** Throughout

**Idea:** Add trace IDs to correlate logs across async operations.

**Impact:** Easier debugging of production issues

---

## 📊 Summary

| Category | Count |
|----------|-------|
| High Priority | 4 |
| Medium Priority | 3 |
| Low Priority | 6 |
| **Total** | **13** |

### nanoclaw Advantages over nanobot:
- ✅ Context window auto-compaction
- ✅ Subagent concurrency limits
- ✅ LRU session cache eviction
- ✅ File caching in ContextBuilder

### nanobot Advantages over nanoclaw:
- ✅ `last_consolidated` tracking (saves API calls)
- ✅ `/new` and `/help` slash commands
- ✅ `_run_agent_loop()` helper (cleaner code)
- ✅ `reasoning_content` preservation in loop

---

## 🚀 Recommended Implementation Order

1. **Add `last_consolidated` to Session** - Immediate API cost savings
2. **Add `/new` and `/help` commands** - Better UX
3. **Refactor `_run_agent_loop()`** - Code maintainability
4. **Add `reasoning_content` to loop** - Support thinking models
5. **Tool output truncation** - Prevent context overflow

---

## 🔧 Quick Wins (Can do now)

These can be implemented in < 30 minutes each:

1. `/new` and `/help` commands
2. `last_consolidated` field
3. Tool output truncation
4. `_run_agent_loop()` extraction
