from abc import ABC, abstractmethod


class BaseState(ABC):
    @abstractmethod
    async def run_enter(self, *args, **kwargs):
        pass

    @abstractmethod
    async def handle_message_of_state(self, *args, **kwargs):
        pass
