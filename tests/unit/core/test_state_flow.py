import asyncio
import pytest
from unittest.mock import AsyncMock

from blue_flow_bot.core.state_flow import StateFlow
from blue_flow_bot.core.registry import StateRegistry


@pytest.mark.asyncio
async def test_constructor_triggers_validate_flow(
    registry_factory, sqlite_db, local_storage
):
    # Arrange: spy on validate_flow
    registry = registry_factory()
    registry.validate_flow = AsyncMock()

    # Act: construct StateFlow
    sf = StateFlow(
        flow_json={"0": {"type": "cutscene", "node_text": "Bye"}},
        registry=registry,
        db=sqlite_db,
        storage=local_storage,
    )

    # Assert: validate_flow was awaited exactly once
    registry.validate_flow.assert_awaited_once_with(
        {"0": {"type": "cutscene", "node_text": "Bye"}}
    )


@pytest.mark.asyncio
async def test_start_polling_makes_get_updates_until_cancel(
    fake_adapter, registry_factory, sqlite_db, local_storage
):
    # Arrange
    registry = registry_factory()
    sf = StateFlow(
        {"0": {"type": "cutscene", "node_text": "Done"}},
        registry,
        sqlite_db,
        local_storage,
    )

    # stub get_updates to yield once then hang
    fake_adapter.get_updates = AsyncMock(side_effect=[[], asyncio.Event().wait()])

    cancel_event = asyncio.Event()

    async def canceller():
        # cancel after a brief moment
        await asyncio.sleep(0.01)
        cancel_event.set()

    # Act
    task = asyncio.create_task(
        sf.start_polling(
            fake_adapter, poll_interval=0.001, cancellation_event=cancel_event
        )
    )
    await canceller()
    await task

    # Assert: get_updates was called at least once
    assert fake_adapter.get_updates.await_count >= 1


@pytest.mark.asyncio
async def test_process_update_advances_state_and_sends_messages(
    fake_adapter, registry_factory, sqlite_db, local_storage
):
    # Arrange: simple flow 0 → cutscene (no next)
    flow = {"0": {"type": "cutscene", "node_text": "The End"}}
    registry = registry_factory()
    sf = StateFlow(flow, registry, sqlite_db, local_storage)

    # stub adapter methods
    fake_adapter.send_message = AsyncMock()
    # Construct a fake update (e.g., a /start command to enter state 0)
    update = {"message": {"chat": {"id": 123}, "text": "/start"}}

    # Act
    await sf.process_update(update, fake_adapter)

    # Assert: send_message was called with our cutscene text
    fake_adapter.send_message.assert_awaited_with(
        chat_id=123, text="The End", **pytest.ANY
    )


@pytest.mark.asyncio
async def test_process_update_propagates_cancelled_error(
    fake_adapter, registry_factory, sqlite_db, local_storage
):
    # Arrange
    registry = registry_factory()

    # Create a flow whose run_enter will raise CancelledError
    class CancelState:
        async def run_enter(self, *args, **kwargs):
            raise asyncio.CancelledError()

        async def handle_message_of_state(self, *args, **kwargs):
            return None

    registry.register_alias = AsyncMock(return_value=None)
    await registry.register_alias("cancel", CancelState)
    flow = {"0": {"type": "cancel", "node_text": ""}}
    sf = StateFlow(flow, registry, sqlite_db, local_storage)

    # Act & Assert: CancelledError should bubble up
    with pytest.raises(asyncio.CancelledError):
        await sf.process_update(
            {"message": {"chat": {"id": 1}, "text": "/start"}}, fake_adapter
        )
