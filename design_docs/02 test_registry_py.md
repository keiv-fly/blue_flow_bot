Here’s a self‐contained **`tests/unit/core/test_registry.py`** blueprint in Markdown. It shows exactly what to import, how to set up your fixtures, and the four async test cases you need to drive your `StateRegistry` into failure modes.

---

```markdown
# tests/unit/core/test_registry.py

This module exercises the three key behaviors of `StateRegistry`:

1. **register_alias() idempotency**  
2. **get() unhappy path**  
3. **validate_flow() error paths**:
   - JSON schema invalid → `FlowValidationError`
   - Unknown `"type"` → `UnknownStateTypeError`
   - Dangling `next` / `next_for_choice` → `DanglingReferenceError`
   - Missing node‐schema keys → `NodeSchemaError`

---

```python
import pytest

# 1. The system under test
from blue_flow_bot.core.registry import StateRegistry
from blue_flow_bot.core.registry import (
    FlowValidationError,
    UnknownStateTypeError,
    DanglingReferenceError,
    NodeSchemaError,
)
from blue_flow_bot.core.base_state import BaseState


# 2. A minimal BaseState subclass for aliasing tests
class DummyState(BaseState):
    async def run_enter(self, *args, **kwargs):
        ...

    async def handle_message_of_state(self, *args, **kwargs):
        ...


@pytest.mark.asyncio
async def test_register_alias_idempotency():
    """
    Registering the same alias twice should raise ValueError
    (or your chosen duplicate‐alias exception).
    """
    registry = StateRegistry()
    # First registration succeeds
    await registry.register_alias("foo", DummyState)
    # Second registration must fail
    with pytest.raises(ValueError):
        await registry.register_alias("foo", DummyState)


@pytest.mark.asyncio
async def test_get_unknown_raises_unknownstate():
    """
    Calling get() with an unregistered type name should
    raise UnknownStateTypeError.
    """
    registry = StateRegistry()
    with pytest.raises(UnknownStateTypeError):
        await registry.get("nonexistent_type")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_flow, expected_exc",
    [
        # 1) Invalid against JSON Schema (missing 'type', etc.)
        (
            {"0": {"node_text": "Hi"}},  
            FlowValidationError
        ),
        # 2) Unknown node type
        (
            {"0": {"type": "nope", "node_text": "Oops"}},  
            UnknownStateTypeError
        ),
        # 3) Dangling reference in `next`
        (
            {
                "0": {"type": "text", "node_text": "Say hi", "next": 1}
            },  
            DanglingReferenceError
        ),
        # 4) Node schema mismatch: choice missing 'choices' key
        (
            {
                "0": {
                    "type": "choice",
                    "node_text": "Pick one",
                    # 'choices' key is mandatory for type 'choice'
                    "next_for_choice": {}
                }
            },
            NodeSchemaError
        ),
    ],
)
async def test_validate_flow_error_paths(bad_flow, expected_exc):
    """
    Each malformed flow should trigger exactly the right exception.
    """
    registry = StateRegistry()
    with pytest.raises(expected_exc):
        await registry.validate_flow(bad_flow)
```

---

### Notes

- Use **`pytest‑asyncio`** so each test can `await` your async methods.
- Import your exception classes straight from `core.registry`.
- For the JSON‐schema check you only need to omit a required key (e.g. `"type"`) to provoke `FlowValidationError`.
- Make sure your `StateRegistry` constructor does *not* auto‐validate—tests call `validate_flow()` explicitly.
- Later on you can **parametrize** more scenarios (e.g. missing `"next_for_choice"` or bad choice keys) in the same style.

With these six async tests in place you’ll lock down the *registry* layer and ensure no bad flows or aliasing mistakes slip through.