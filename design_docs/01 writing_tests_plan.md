Below is the same **test‑first roadmap**, rewritten to use **`aioresponses`** (plus its `pytest‑aioresponses` helper) instead of **respx**. Everything else — coverage targets, tiers, CI gates — stays the same.

---

## 1 · Ground Rules & Success Criteria  

| Aspect | Target |
|--------|--------|
| **Coverage** | ≥ 90 % lines **and** 100 % of public branches in `core/` & `domain/` |
| **Async fidelity** | No `asyncio.run()` inside tests; every coroutine awaited by the runner |
| **Repeatability** | Tests are hermetic; nothing reaches the real Telegram servers or filesystem outside `tmp_path` |
| **Speed budget** | Full suite ≤ 60 s locally, ≤ 2× in CI |
| **CI gate** | *Only* merges that keep all green badges & coverage target |

---

## 2 · Toolchain & Conventions  

* **Runner** – `pytest` 7 + `pytest‑asyncio`.  
* **HTTP mocks** – **`aioresponses`** (and its `pytest‑aioresponses` plugin) patches `aiohttp.ClientSession` in‑place; no `httpx` dependency. citeturn1search0turn1search1  
* **DB** – `pytest‑docker` spins Postgres 16 in ≈ 3 s; `aiosqlite` uses `:memory:`.  
* **FS** – `tmp_path` fixture; `aiofiles` writes inside it.  
* **Static** – Ruff (lint), MyPy (strict), `jsonschema-async`.  
* **Property‑based** – Hypothesis for flow‑validation fuzzing.  
* **Perf** – `pytest‑benchmark` for p95 latency budget.  
* **Markers** –  
  * `unit`, `contract`, `integration`, `perf`  
  * default run skips `perf`; CI job runs them nightly.  
* **File layout**  

```
tests/
├─ unit/
│   └─ core/…  domain/…  adapters/…  persistence/…
├─ contract/
│   └─ bot_api/
├─ integration/
│   ├─ flows/         # sample JSON flows
│   └─ docker/        # compose.yaml (pg + fake‑telegram)
├─ perf/
└─ conftest.py        # shared async fixtures & factories
```

---

## 3 · Shared Fixtures & Utilities  

| Fixture | Purpose |
|---------|---------|
| `event_loop` | Swap in `uvloop` if available. |
| `registry_factory` | Ready‑made `StateRegistry` with built‑ins. |
| `sample_flow` | Valid JSON from spec §7. |
| `aio_mock` | **Session‑level** `aioresponses` context; auto‑yield to tests. |
| `fake_adapter` | `RawHttpAdapter` wired to normal `aiohttp.ClientSession`; calls are intercepted by `aio_mock`. |
| `sqlite_db` / `pg_db` | Async engines with clean teardown. |
| `local_storage` | `LocalFSStorage` rooted in `tmp_path`. |
| `state_flow` | Assembles `StateFlow`; awaits cleanup. |
| `voice_message` | Factory for Telegram‑style voice update dicts. |

All fixtures live in `tests/conftest.py`.  
Heavy fixtures (`pg_db`) scoped `session` to reduce startup time.

---

## 4 · Static & Schema Tests (Tier 0)  

1. **Ruff & MyPy** – fail fast in the first CI stage.  
2. **Flow JSON schema** – Hypothesis + `jsonschema-async` barrage.  
3. **Doc code‑block check** – every JSON/Python snippet in the spec parsed & validated.

---

## 5 · Unit Tests (Tier 1)  

Identical to the earlier outline, but every test that hits the network now depends on **`aio_mock`** instead of `respx`.

### Example snippet

```python
async def test_send_message(fake_adapter, aio_mock):
    aio_mock.post(
        "https://api.telegram.org/bot123/sendMessage",
        payload={"ok": True, "result": {"message_id": 1}},
    )
    await fake_adapter.send_message(chat_id=1, text="hi")
    assert aio_mock.call_count == 1
```

`aio_mock.call_count` lets you assert retry/back‑pressure behaviour the same way we previously used `respx`.

All other unit targets (§5.1‑5.5 in the original plan) remain unchanged.

---

## 6 · Contract Tests (Tier 2) — “Detect API Drift”  

`aioresponses` does not ship first‑class cassette storage, so we store **golden JSON fixtures** (`tests/contract/bot_api/*.json`). Each test registers the fixture as the response body and asserts that our adapter emits the exact request structure.

```python
@pytest.mark.contract
async def test_send_voice_contract(fake_adapter, aio_mock, load_json):
    payload = load_json("send_voice_response.json")
    aio_mock.post("*/sendVoice", payload=payload)
    await fake_adapter.send_voice(chat_id=1, voice=b"\x00\x01", duration=3)
    # drift detection: compare *sent* JSON against frozen snapshot
    sent = aio_mock.requests[("POST", URL("https://api.telegram.org/bot123/sendVoice"))][0].kwargs["json"]
    assert sent == load_json("send_voice_request.json")
```

If Telegram changes its field set, snapshot comparison fails and CI signals a drift.

---

## 7 · Integration Tests (Tier 3)  

Exactly the same docker‑compose stack as before (Postgres + fake Telegram server implemented with `aiohttp.web`).  
Because these tests run against a **live HTTP server**, they do **not** use `aioresponses`.

Scenarios:

* **Happy path** through every built‑in state.  
* **Failure matrix** driven from spec §13.  
* **Concurrency** check: 100 parallel chats, semaphore never exceeds 25.

---

## 8 · Performance & Concurrency (Tier 4)  

No change, but note that `aioresponses` is disabled (via marker skip) in these benchmarks so they exercise real sockets.

---

## 9 · Continuous Integration Pipeline  

Same GitHub Actions workflow – only swap in an extra `pip install pytest-aioresponses` step before running the suite.

---

## 10 · Developer Workflow Cheat‑Sheet  

1. **Red** – write a failing test under `tests/unit/` using `aio_mock`.  
2. **Green** – implement code until tests pass.  
3. **Blue** – refactor, run `ruff –fix` & `pytest -q`.  
4. **Commit** (`feat:`, `fix:`, `test:` …).  
5. **Push PR** – CI enforces all of the above.

---

### Summary  

Replacing **respx** with **aioresponses** means:

* One extra dev‑dependency (`pytest‑aioresponses`) and a fixture that patches `aiohttp.ClientSession`.
* Contract tests store **golden request/response JSON** instead of YAML cassettes.
* All retry, semaphore and error‑handling assertions are still expressible (via `aio_mock.call_count`, `aio_mock.requests`, exception injection, etc.).

The rest of the tiered strategy, coverage ambitions and CI guardrails stay intact.