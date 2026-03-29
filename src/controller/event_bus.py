from asyncio import create_task
from collections import defaultdict
from typing import Any, Callable, Coroutine, TypeAlias, Optional

Callback: TypeAlias = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    _instance: Optional["EventBus"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._subscribers: dict[str, list[Callback]] = defaultdict(list)
        self._initialized = True

    def subscribe(self, event_type: str, handler: Callback) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type: str, *args: Any) -> None:
        if handlers := self._subscribers.get(event_type, []):
            for handler in handlers:
                create_task(handler(*args))