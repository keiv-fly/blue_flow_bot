# tests/unit/core/test_registry.py

import pytest

from blue_flow_bot.core.registry import (
    StateRegistry,
    FlowValidationError,
    UnknownStateTypeError,
    DanglingReferenceError,
    NodeSchemaError,
)
from blue_flow_bot.core.base_state import BaseState


class DummyState(BaseState):
    """
    Minimal BaseState subclass for aliasing tests.
    """

    async def run_enter(self, bot, chat_id, db, context=None):
        # no-op
        return

    async def handle_message_of_state(
        self, bot, chat_id, db, text, message, context, storage, iteration
    ):
        # no-op
        return None


@pytest.mark.asyncio
async def test_register_alias_idempotency():
    """
    Registering the same alias twice should raise ValueError
    (duplicate alias not permitted).
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
        # 1) Missing required 'type' key → schema validation error
        (
            {0: {"node_text": "Hi"}},
            FlowValidationError,
        ),
        # 2) Unknown node 'type' → UnknownStateTypeError
        (
            {0: {"type": "nope", "node_text": "Oops"}},
            UnknownStateTypeError,
        ),
        # 3) Dangling reference in 'next' → DanglingReferenceError
        (
            {
                0: {
                    "type": "text",
                    "node_text": "Say something",
                    "next": 1,
                    "key_to_save": "foo",
                    "min_words": 1,
                }
            },
            DanglingReferenceError,
        ),
        # 4) Choice node missing 'choices' key → NodeSchemaError
        (
            {
                0: {
                    "type": "choice",
                    "node_text": "Pick one",
                    # 'choices' is required for choice nodes
                    "next_for_choice": {"a": 1},
                }
            },
            NodeSchemaError,
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


@pytest.mark.asyncio
async def test_validate_flow_valid_three_nodes():
    """
    A flow with 3 valid nodes should pass validation.
    """
    registry = StateRegistry()

    # Register required state types
    await registry.register_alias("text", DummyState)
    await registry.register_alias("choice", DummyState)

    valid_flow = {
        0: {
            "type": "text",
            "node_text": "Welcome to the flow",
            "next": 1,
            "key_to_save": "welcome_message",
            "min_words": 1,
        },
        1: {
            "type": "choice",
            "node_text": "Choose an option",
            "choices": ["Option A", "Option B"],
            "next_for_choice": {"Option A": 2, "Option B": 2},
        },
        2: {
            "type": "text",
            "node_text": "Thank you for your choice",
            "key_to_save": "final_message",
            "min_words": 1,
        },
    }

    # This should not raise any exceptions
    await registry.validate_flow(valid_flow)
