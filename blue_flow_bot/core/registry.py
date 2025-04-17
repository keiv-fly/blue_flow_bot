# blue_flow_bot/core/registry.py

from typing import Dict, Type
from blue_flow_bot.core.base_state import BaseState


class FlowValidationError(Exception):
    """Raised when a flow JSON fails schema validation."""

    pass


class UnknownStateTypeError(Exception):
    """Raised when a flow references an unregistered state type."""

    pass


class DanglingReferenceError(Exception):
    """Raised when a flow references a non-existent next state."""

    pass


class NodeSchemaError(Exception):
    """Raised when a node is missing type-specific required keys."""

    pass


class StateRegistry:
    """
    Maps state type names to BaseState subclasses, and validates flow definitions.
    """

    enable_context: bool = False

    def __init__(self):
        # Pre-register built-in state types
        self._registry: Dict[str, Type[BaseState]] = {
            "choice": BaseState,
            "text": BaseState,
            "rich_text": BaseState,
            "tg_username": BaseState,
            "voice_upload": BaseState,
            "file_upload": BaseState,
            "cutscene": BaseState,
        }

    async def register_alias(self, type_name: str, cls: Type[BaseState]) -> None:
        """
        Register a new alias mapping a type_name to a BaseState subclass.
        Raises ValueError if the alias already exists.
        """
        if type_name in self._registry:
            raise ValueError(f"Type alias '{type_name}' already registered")
        self._registry[type_name] = cls

    async def get(self, type_name: str) -> Type[BaseState]:
        """
        Look up a registered BaseState subclass by its type name.
        Raises UnknownStateTypeError if not found.
        """
        try:
            return self._registry[type_name]
        except KeyError:
            raise UnknownStateTypeError(f"Unknown state type '{type_name}'")

    async def validate_flow(self, flow_json: dict[int, dict]) -> None:
        """
        Perform consistency checks on a flow definition:
          1) Every node has a 'type' key → FlowValidationError
          2) Every 'type' is registered → UnknownStateTypeError
          3) Type-specific node schema → NodeSchemaError
          4) All 'next' & 'next_for_choice' IDs exist → DanglingReferenceError
        """
        # 1) Basic schema: 'type' present
        for node_id, node in flow_json.items():
            if "type" not in node:
                raise FlowValidationError(f"Node {node_id!r} missing 'type'")

        # 2) Known types
        for node_id, node in flow_json.items():
            t = node["type"]
            if t not in self._registry:
                raise UnknownStateTypeError(f"Unknown state type '{t}'")

        # 3) Node-specific schema checks
        for node_id, node in flow_json.items():
            t = node["type"]
            if t == "choice":
                if "choices" not in node or "next_for_choice" not in node:
                    raise NodeSchemaError(
                        f"Choice node {node_id!r} missing 'choices' or 'next_for_choice'"
                    )

        # 4) Reference integrity
        valid_ids = {int(i) for i in flow_json.keys()}
        for node_id, node in flow_json.items():
            # single next
            if "next" in node:
                dest = node["next"]
                if dest not in valid_ids:
                    raise DanglingReferenceError(
                        f"Node {node_id!r} references unknown next {dest}"
                    )
            # choice nexes
            if "next_for_choice" in node:
                for choice, dest in node["next_for_choice"].items():
                    if dest not in valid_ids:
                        raise DanglingReferenceError(
                            f"Node {node_id!r} choice {choice!r} references unknown next {dest}"
                        )
