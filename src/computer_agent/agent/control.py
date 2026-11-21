import asyncio
from collections import deque
from dataclasses import dataclass
from typing import AsyncIterator


class TaskStopped(Exception):
    pass


@dataclass(frozen=True)
class ControlEvent:
    event_id: int
    event: str
    data: dict[str, object]


class TaskControl:
    def __init__(self) -> None:
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._paused_at_boundary = False
        self._stopping = False
        self._finished = False
        self._next_event_id = 1
        self._events: deque[ControlEvent] = deque(maxlen=100)
        self._subscribers: set[asyncio.Queue[ControlEvent]] = set()
        self.latest_observation: dict[str, object] | None = None
        self.latest_frame: dict[str, object] | None = None
        self.frames: list[dict[str, object]] = []

    @property
    def paused(self) -> bool:
        return self._paused_at_boundary

    @property
    def pause_requested(self) -> bool:
        return not self._resume_event.is_set() and not self._stopping

    @property
    def stopping(self) -> bool:
        return self._stopping

    @property
    def finished(self) -> bool:
        return self._finished

    def pause(self) -> None:
        self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    def stop(self) -> None:
        self._stopping = True
        self._resume_event.set()

    def publish(self, event: str, data: dict[str, object]) -> None:
        control_event = ControlEvent(self._next_event_id, event, data)
        self._next_event_id += 1
        self._events.append(control_event)
        if event == "observation":
            self.latest_observation = data
        elif event == "frame":
            self.latest_frame = data
            self.frames.append(data)
            if len(self.frames) > 50:
                self.frames = self.frames[-50:]
        for subscriber in tuple(self._subscribers):
            if subscriber.full():
                subscriber.get_nowait()
            subscriber.put_nowait(control_event)

    def mark_finished(self) -> None:
        self._finished = True

    async def wait_until_resumed(self) -> None:
        if self._stopping:
            raise TaskStopped
        if not self._resume_event.is_set():
            self._paused_at_boundary = True
            self.publish("status", {"status": "paused"})
            await self._resume_event.wait()
            self._paused_at_boundary = False
        if self._stopping:
            raise TaskStopped

    async def events(self, after_id: int = 0) -> AsyncIterator[ControlEvent | None]:
        queue: asyncio.Queue[ControlEvent] = asyncio.Queue(maxsize=100)
        for event in self._events:
            if event.event_id > after_id:
                queue.put_nowait(event)
        self._subscribers.add(queue)
        try:
            while not self._finished or not queue.empty():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    if not self._finished:
                        yield None
        finally:
            self._subscribers.discard(queue)
