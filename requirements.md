# **Blue Flow Bot — *Full Functional & API Specification*  
(v 0.4.0 “Rich‑Media JSON” baseline, **Local‑FS only**)**

_Last updated: **17 April 2025**_  

---

## 1 · Mission Statement  
Create a **concise, production‑ready Python package** that converts a declared **JSON Flow Definition** plus **Python state classes** into a Telegram bot using **raw Bot API HTTPS**.  
It must handle text, inline‑buttons, voice notes and file uploads, persist everything, and *self‑test* at import‑time that the JSON file and the state registry line up correctly.

---

## 2 · Scope  

| Included | Excluded |
|----------|----------|
| Long‑poll & webhook operation | Other chat platforms |
| Built‑in state patterns: choice, text, rich‑text, username, cut‑scene, voice‑upload, file‑upload | Inline games, location, payments |
| SQLite & Postgres back‑ends, **local‑FS attachment store** | Remote/Cloud object stores |
| Optional per‑chat **Context** | Cross‑chat shared state |
| LLM profanity / relevance hooks (pluggable) | Speech‑to‑text, virus scanning |

---

## 3 · Vocabulary  

| Term | Meaning |
|------|---------|
| **Flow JSON** | Mapping of integer state IDs → node dicts. |
| **State** | Python subclass of `BaseState`. |
| **Registry** | Maps `"type"` strings in JSON → State classes. |
| **Context** | Per‑chat mutable dict persisted in DB. |
| **StorageBackend** | Persists downloaded attachments and returns URLs. |

---

## 4 · Top‑Level Architecture  
```
┌─────────────┐   JSON Flow   ┌────────────┐  Telegram Update  ┌──────────────┐
│  Registry   │◀─────────────▶│ StateFlow  │◀──────────────────│ RawHttpAdapter│
└─────────────┘               └─────┬──────┘                  └────┬──────────┘
                                    │ checks & persistence          │ HTTPS
                                    ▼                               ▼
                              ┌───────────┐                   Telegram Bot API
                              │ BaseState │
                              └───────────┘
```

---

## 5 · Package Layout  
```
blue_flow_bot/
├─ adapters/
│  └─ http.py                # Raw Bot‑API transport
├─ core/
│  ├─ engine.py              # BotEngine
│  ├─ state_flow.py          # StateFlow
│  ├─ registry.py            # StateRegistry + JSON validator
│  ├─ context.py             # Context
│  └─ base_state.py          # BaseState ABC
├─ domain/                   # Built‑ins
│  ├─ choice.py              # ChoiceState
│  ├─ text.py                # TextState
│  ├─ rich_text.py           # RichTextState
│  ├─ tg_username.py         # TelegramUsernameState
│  ├─ voice_upload.py        # VoiceUploadState
│  ├─ file_upload.py         # FileUploadState
│  └─ cutscene.py            # CutsceneState
├─ persistence/
│  ├─ backend.py             # abstract PersistenceBackend
│  ├─ sqlite_backend.py
│  ├─ pg_backend.py
│  └─ attachments.py         # StorageBackend ABC + LocalFS impl
├─ validators/
│  └─ llm.py
└─ cli/
   └─ main.py                # `bfb run-bot …`
```

---

## 6 · Database Schema (Postgres)  
*(SQLite uses identical logical schema; `JSONB` stored as TEXT.)*  

```sql
CREATE TABLE chats (
    chat_id       BIGINT PRIMARY KEY,
    current_state INTEGER  NOT NULL,
    iteration     INTEGER  DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id          BIGSERIAL PRIMARY KEY,
    chat_id     BIGINT    NOT NULL,
    tg_msg_id   BIGINT    NOT NULL,
    from_user   BOOLEAN   NOT NULL,
    body        TEXT,
    state_id    INTEGER,
    iteration   INTEGER,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE kv_store (
    chat_id    BIGINT,
    state_id   INTEGER,
    key        TEXT,
    val        TEXT,
    iteration  INTEGER DEFAULT 0,
    try_no     INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, state_id, key, iteration)
);

CREATE TABLE attachments (
    id          BIGSERIAL PRIMARY KEY,
    chat_id     BIGINT      NOT NULL,
    state_id    INTEGER     NOT NULL,
    telegram_id TEXT        NOT NULL,
    storage_url TEXT        NOT NULL,
    mime_type   TEXT,
    bytes       BIGINT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE user_ctx (
    chat_id   BIGINT PRIMARY KEY,
    value     JSONB   NOT NULL,
    ver       INTEGER NOT NULL
);
```

---

## 7 · Flow Definition (JSON, canonical)  
```json
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

## 8 · Class & Method Catalogue (excerpts)  

### 8.1  `core.registry.StateRegistry`
```python
class StateRegistry:
    enable_context: bool = False

    def register_alias(self, type_name: str, cls: type[BaseState]) -> None: ...
    def get(self, type_name: str) -> type[BaseState]: ...
    def validate_flow(self, flow_json: dict[int, dict]) -> None: ...
```
`validate_flow()` is **invoked automatically** inside `StateFlow.__init__`.

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
    ): ...

    async def process_update(self, update: dict, adapter: RawHttpAdapter) -> None: ...
```

---

### 8.3  `domain.voice_upload.VoiceUploadState` (contract)
```python
class VoiceUploadState(BaseState):
    async run_enter(...): ...
    async handle_message_of_state(
        bot, chat_id, db, text, message, context, storage, iteration
    ) -> tuple[int, str] | None
```
*Reject non‑voice → re‑prompt user.*

---

### 8.4  `persistence.attachments.StorageBackend`
```python
class StorageBackend(ABC):
    async def save(
        self,
        chat_id: int,
        state_id: int,
        file_name: str,
        mime: str,
        data: bytes,
    ) -> str: ...

    async def delete(self, url: str) -> None: ...
```
**Implementation provided:** `LocalFSStorage` (writes under a configurable root).

---

## 9 · Transport Additions  
```python
class RawHttpAdapter:
    async def send_voice(...): ...
    async def send_document(...): ...
    async def get_file(file_id: str) -> dict: ...
    async def download_file(file_path: str) -> bytes: ...
```
All methods honour 3× retry & a global semaphore (25 req/s).

---

## 10 · Automated Consistency Tests (built‑in)  

| # | Check | Error raised |
|---|-------|--------------|
| 1 | JSON valid against schema | `FlowValidationError` |
| 2 | Each `"type"` has registered class | `UnknownStateTypeError` |
| 3 | All `next`/`next_for_choice` refer to existing IDs | `DanglingReferenceError` |
| 4 | Built‑in states support required keys | `NodeSchemaError` |

These run synchronously when `StateFlow` is instantiated.

---

## 11 · Testing Strategy  

| Tier | Tooling | Goal |
|------|---------|------|
| **Static** | Ruff + MyPy + JSON‑schema | 0 warnings |
| **Unit** | pytest‑asyncio | ≥ 90 % in `core/` & `domain/` |
| **Contract** | Recorded cassettes vs Telegram Bot API | Detect API drift |
| **Integration** | docker‑compose (Postgres + mock Telegram) | End‑to‑end flow including uploads |
| **Consistency** | `registry.validate_flow()` on every sample flow | Ensure docs & code align |

CI pipeline: GitHub Actions → tox matrix (3.9‑3.12).

---

## 12 · CLI Usage  
```bash
bfb run-bot \
   --token   $BOT_TOKEN                         \
   --flow    ./flow.json                       \
   --states  mybot.states                      \
   --db      pg://user:pass@host/dbname        \
   --storage fs:/var/bfb/uploads               \
   --enable-context
```
`--storage` must reference a **local directory** (prefix `fs:`).

---

## 13 · Non‑Functional Targets  

| Metric | Target |
|--------|--------|
| Latency (p95) | ≤ 150 ms / update @ 100 chats / s (2 vCPU) |
| Max upload | 20 MB (Telegram limit) |
| Download retry | 3× (1 s → 3 s → 9 s) |
| Availability | 99.9 % yearly |
| Observability | Structured JSON logs + Prometheus metrics + OTEL traces |

---

## 14 · Error Handling Matrix (excerpt)  

| Layer | Error | Action |
|-------|-------|--------|
| Adapter.download_file | 5xx after retries | Send “Upload failed, try again”, stay on same state |
| VoiceUploadState | too‑long voice | Prompt with reason, do not advance |
| FileUploadState | wrong MIME / size | Same |
| DB save_context conflict | Retry once, log if fails |
| Registry validation fail | Abort startup (exit code 1) |

---

## 15 · Versioning & Migration  

* This document defines **v 0.4.0**; bumps MINOR over 0.3 (adds rich‑media + JSON flow).  
* DB migration = create `attachments` table.  
* Previous flows keep working after converting YAML → JSON and renaming keys (`question_to_save` → `key_to_save`).  

---

## 16 · Security Notes  

* Token only via env/CLI, never stored in code.  
* Attachments saved to local disk under restrictive permissions; originals deleted after write.  
* Optional AES‑GCM encryption for `kv_store.val` and `user_ctx.value`.  
* JSON flow validated; no dynamic code executed.  

---

## 17 · Open Items  

| # | Topic | Status |
|---|-------|--------|
| 48 | Optional speech‑to‑text plug‑in for voice uploads | Backlog |
| 49 | ClamAV integration for file uploads | Design |
| 50 | Rate‑limit buckets per Bot API method | Research |

---

### **Author’s mantra**  
> “Fail fast at import ‑ ship small pieces ‑ log ****everything ‑ let nothing undefined through.”