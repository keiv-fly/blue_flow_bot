# **Blue Flow Bot — *Full Functional & API Specification***    
(v **0.5.0 “Async‑Everywhere”** baseline, **Local‑FS only**)

_Last updated: **17 April 2025**_  

---

## 1 · Mission Statement  
Deliver a **concise, production‑ready asynchronous Python package** that converts a declared **JSON Flow Definition** plus **Python state classes** into a Telegram bot using **raw Bot API HTTPS**.  
All public behaviour **must be implemented with `async` / `await`**, enabling clean concurrency, high throughput and consistent cancellation semantics.  
It must handle text, inline‑buttons, voice notes and file uploads, **persist everything**, and *self‑test* at import‑time that the JSON file and the state registry line up correctly.

---

## 2 · Scope  

| Included (async) | Excluded |
|------------------|----------|
| Long‑poll **and** webhook operation | Other chat platforms |
| Built‑in async state patterns: choice, text, rich‑text, username, cut‑scene, voice‑upload, file‑upload | Inline games, location, payments |
| SQLite & Postgres back‑ends via **async drivers**;<br>**local‑FS async attachment store** | Remote / Cloud object stores |
| Optional per‑chat **Context** | Cross‑chat shared state |
| Pluggable LLM profanity / relevance hooks (async) | Speech‑to‑text, virus scanning |

---

## 3 · Vocabulary  

| Term | Meaning |
|------|---------|
| **Flow JSON** | Mapping of integer state IDs → node dicts. |
| **State** | Python subclass of `BaseState`. |
| **Registry** | Maps `"type"` strings in JSON → State classes. |
| **Context** | Per‑chat mutable dict persisted asynchronously in DB. |
| **StorageBackend** | Persists downloaded attachments and returns URLs. |

---

## 4 · Top‑Level Architecture  

```
┌─────────────┐   JSON Flow   ┌────────────┐  Telegram Update  ┌──────────────┐
│  Registry   │◀─────────────▶│ StateFlow  │◀──────────────────│ RawHttpAdapter│
└─────────────┘               └─────┬──────┘                  └────┬──────────┘
                                    │ async checks & persistence    │ HTTPS (async)
                                    ▼                               ▼
                              ┌───────────┐                   Telegram Bot API
                              │ BaseState │                   (handled with aiohttp)
                              └───────────┘
```

*All horizontal interactions are awaitable coroutines protected by back‑pressure primitives (`asyncio.Semaphore`, `asyncio.Queue`, etc.).*

---

## 5 · Package Layout  

```
blue_flow_bot/
├─ adapters/
│  └─ http.py                # Raw Bot‑API transport (aiohttp)
├─ core/
│  ├─ engine.py              # BotEngine (async entry‑points)
│  ├─ state_flow.py          # StateFlow
│  ├─ registry.py            # StateRegistry + JSON validator
│  ├─ context.py             # Context
│  └─ base_state.py          # BaseState ABC
├─ domain/                   # Built‑ins (all async)
│  ├─ choice.py
│  ├─ text.py
│  ├─ rich_text.py
│  ├─ tg_username.py
│  ├─ voice_upload.py
│  ├─ file_upload.py
│  └─ cutscene.py
├─ persistence/
│  ├─ backend.py             # abstract PersistenceBackend
│  ├─ sqlite_backend.py      # aiosqlite
│  ├─ pg_backend.py          # asyncpg
│  └─ attachments.py         # StorageBackend ABC + LocalFS impl (aiofiles)
├─ validators/
│  └─ llm.py
└─ cli/
   └─ main.py                # `bfb run-bot …`
```

---

## 6 · Database Schema (Postgres)  

*(SQLite keeps the identical logical schema; `JSONB` stored as TEXT.)*—unchanged from 0.4.0.

---

## 7 · Flow Definition (JSON, canonical)  

```jsonc
{
  "0": {
    "type": "choice",
    "node_text": "Ready?",
    "choices": {"go": "Let's go!"},
    "next_for_choice": {"go": 1}
  },
  "1": {
    "type": "text",
    "node_text": "Tell me something interesting.",
    "key_to_save": "user_fact",
    "min_words": 4,
    "next": 10
  },
  "10": {
    "type": "voice_upload",
    "node_text": "🎤  Send a voice message ≤ 60 s",
    "max_seconds": 60,
    "key_to_save": "feedback_voice_url",
    "next": 20
  },
  "20": {
    "type": "file_upload",
    "node_text": "📄  Upload a PDF (≤ 5 MB)",
    "allowed_mime": ["application/pdf"],
    "max_mb": 5,
    "key_to_save": "brief_url",
    "next": 99
  },
  "99": {
    "type": "cutscene",
    "node_text": "Thanks for chatting!"
  }
}
```

> **Validation JSON‑Schema** is shipped at `blue_flow_bot/flow_schema.json`.

---

## 8 · Public Class & Method Catalogue (complete)  

> **Rule of thumb:** **Every public method is an `async def`** unless explicitly marked *sync‑only* (currently none). All I/O must use await‑compatible libraries.

### 8.1  `core.registry.StateRegistry`

```python
class StateRegistry:
    enable_context: bool = False

    async def register_alias(self, type_name: str, cls: type[BaseState]) -> None: ...
    async def get(self, type_name: str) -> type[BaseState]: ...
    async def validate_flow(self, flow_json: dict[int, dict]) -> None: ...
```
`validate_flow()` **is awaited automatically** inside `StateFlow.__init__`.

---

### 8.2  `core.state_flow.StateFlow`

```python
class StateFlow:
    def __init__(
        self,
        flow_json: dict[int, dict],
        registry: StateRegistry,
        db: PersistenceBackend,
        storage: StorageBackend,
    ) -> None:  # constructor stays sync for cheap work; heavy work deferred
        ...

    async def start_polling(
        self,
        adapter: RawHttpAdapter,
        *,
        poll_interval: float = 0.5,
        cancellation_event: asyncio.Event | None = None,
    ) -> None: ...

    async def process_update(
        self,
        update: dict,
        adapter: RawHttpAdapter,
    ) -> None: ...
```

---

### 8.3  `domain.voice_upload.VoiceUploadState` (contract)

```python
class VoiceUploadState(BaseState):
    async def run_enter(
        self,
        bot: RawHttpAdapter,
        chat_id: int,
        db: PersistenceBackend,
        context: Context | None,
    ) -> None: ...

    async def handle_message_of_state(
        bot: RawHttpAdapter,
        chat_id: int,
        db: PersistenceBackend,
        text: str | None,
        message: dict,
        context: Context | None,
        storage: StorageBackend,
        iteration: int,
    ) -> tuple[int, str] | None: ...
```
*Reject non‑voice → re‑prompt user.*

---

### 8.4  `persistence.attachments.StorageBackend`

```python
class StorageBackend(ABC):
    @abstractmethod
    async def save(
        self,
        chat_id: int,
        state_id: int,
        file_name: str,
        mime: str,
        data: bytes,
    ) -> str: ...

    @abstractmethod
    async def delete(self, url: str) -> None: ...
```
**Implementation provided:** `LocalFSStorage` (`aiofiles`, streaming write).

---

### 8.5  `adapters.http.RawHttpAdapter` (excerpt)

```python
class RawHttpAdapter:
    def __init__(self, token: str, *, session: aiohttp.ClientSession | None = None) -> None: ...

    # Bots → users
    async def send_message(...): ...
    async def send_voice(...): ...
    async def send_document(...): ...

    # Users → bots
    async def get_updates(...): ...
    async def answer_callback_query(...): ...

    # File ops
    async def get_file(file_id: str) -> dict: ...
    async def download_file(file_path: str) -> bytes: ...
```
All methods honour **3× retry** + **global semaphore (25 req/s)**.

---

## 9 · Automated Consistency Tests  

| # | Check (awaitable) | Error raised |
|---|-------------------|--------------|
| 1 | JSON valid against schema (`jsonschema‑async`) | `FlowValidationError` |
| 2 | Each `"type"` has registered class | `UnknownStateTypeError` |
| 3 | All `next` / `next_for_choice` refer to existing IDs | `DanglingReferenceError` |
| 4 | Built‑in states support required keys | `NodeSchemaError` |

These run **as awaited coroutines** inside `StateFlow.__init__`.

---

## 10 · Testing Strategy  

| Tier | Tooling | Goal |
|------|---------|------|
| **Static** | Ruff + MyPy + JSON‑schema | 0 warnings |
| **Unit** | pytest‑asyncio | ≥ 90 % in `core/` & `domain/` |
| **Contract** | Recorded cassettes (respx) vs Telegram Bot API | Detect API drift |
| **Integration** | docker‑compose (Postgres + mock Telegram) | Full async path including uploads |
| **Consistency** | `registry.validate_flow()` on every sample flow | Ensure docs & code align |

CI pipeline: GitHub Actions → tox matrix (Py 3.9 – 3.12).

---

## 11 · CLI Usage  

```bash
bfb run-bot \
   --token   $BOT_TOKEN                         \
   --flow    ./flow.json                       \
   --states  mybot.states                      \
   --db      pg://user:pass@host/dbname        \
   --storage fs:/var/bfb/uploads               \
   --enable-context
```
Internally spawns an `asyncio` event loop and blocks until cancelled (SIGINT/SIGTERM).

---

## 12 · Non‑Functional Targets  

| Metric | Target |
|--------|--------|
| Latency (p95) | ≤ 150 ms /update @ 100 chats /s (2 vCPU) |
| Max upload | 20 MB (Telegram limit) |
| Download retry | 3× (1 s → 3 s → 9 s) |
| Memory footprint | ≤ 100 MB RSS @ 1 000 concurrent chats |
| Availability | 99.9 % yearly |
| Observability | Structured JSON logs + Prometheus metrics + OTEL traces (async exporters) |

---

## 13 · Error Handling Matrix (excerpt)  

| Layer | Error | Action |
|-------|-------|--------|
| Adapter.download_file | 5xx after retries | Await `bot.send_message(…)` → “Upload failed, try again”, stay on same state |
| VoiceUploadState | too‑long voice | Prompt with reason, do not advance |
| FileUploadState | wrong MIME / size | Same |
| DB save_context conflict | Retry once with exponential back‑off; log if fails |
| Registry validation fail | Abort startup (exit code 1) |

---

## 14 · Versioning & Migration  

* This document defines **v 0.5.0**; bumps MINOR over 0.4 (converts entire surface to async, keeps feature‑parity).  
* DB schema unchanged.  
* Code migrators: run `blue_flow_bot.tools.sync_to_async_fixer` on custom states (< 500 LoC).  

---

## 15 · Security Notes  

* Token only via env/CLI, never stored in code.  
* Attachments saved to local disk with `0600` perms; originals deleted after write.  
* Optional AES‑GCM encryption for `kv_store.val` and `user_ctx.value` — performed in a thread‑pool executor to avoid blocking.  
* JSON flow validated; no dynamic code executed.  
* Global `asyncio.CancelledError` propagation → immediate graceful shutdown.  

---

## 16 · Open Items  

| # | Topic | Status |
|---|-------|--------|
| 48 | Optional speech‑to‑text plug‑in for voice uploads | Backlog |
| 49 | ClamAV integration for file uploads | Design |
| 50 | Rate‑limit buckets per Bot API method | Research |

---

### **Author’s mantra**  
> “Fail fast at import ‑ ship small async pieces ‑ log ****everything ‑ let nothing undefined through.”