from asyncio import create_task, get_running_loop
from collections import defaultdict
from inspect import isawaitable
from typing import Any, Callable, Coroutine, TypeAlias, Optional

Callback: TypeAlias = Callable[..., Any]


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
                result = handler(*args)
                if isawaitable(result):
                    create_task(result)

    def publish_sync(self, event_type: str, *args: Any) -> None:
        if handlers := self._subscribers.get(event_type, []):
            for handler in handlers:
                result = handler(*args)
                if isawaitable(result):
                    try:
                        loop = get_running_loop()
                    except RuntimeError:
                        continue
                    loop.create_task(result)