import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

QueueKey = tuple[str, ...]


class CommandQueue:
    """
    Order commands sharing a member or code while unrelated commands run freely.
    """

    def __init__(self) -> None:
        self.tails: dict[QueueKey, asyncio.Future[None]] = {}

    @asynccontextmanager
    async def wait(self, keys: list[QueueKey]) -> AsyncGenerator[None, None]:
        # Reserve every queue before waiting, so a later claimant cannot overtake.
        predecessors = {self.tails[key] for key in keys if key in self.tails}
        finished: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        for key in keys:
            self.tails[key] = finished

        ready = asyncio.gather(*(asyncio.shield(previous) for previous in predecessors))
        try:
            await asyncio.shield(ready)
            yield
        finally:
            # Cancellation must preserve the predecessor chain until it is done.
            if ready.done():
                self._release(keys, finished)
            else:
                ready.add_done_callback(lambda _: self._release(keys, finished))

    def _release(self, keys: list[QueueKey], finished: asyncio.Future[None]) -> None:
        finished.set_result(None)
        for key in keys:
            if self.tails.get(key) is finished:
                del self.tails[key]
