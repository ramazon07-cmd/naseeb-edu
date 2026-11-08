import time


class TtlCache:
    """A few seconds of memory per chat, so a double tap does not hit the backend twice."""

    def __init__(self, seconds, clock=time.monotonic, max_items=2000):
        self._seconds = seconds
        self._clock = clock
        self._max = max_items
        self._items = {}

    def get(self, key):
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry[0] <= self._clock():
            del self._items[key]
            return None
        return entry[1]

    def set(self, key, value, seconds=None):
        if len(self._items) >= self._max:
            now = self._clock()
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            if len(self._items) >= self._max:
                self._items.clear()
        self._items[key] = (self._clock() + (self._seconds if seconds is None else seconds), value)

    def drop_chat(self, chat_id):
        for key in [k for k in self._items if k[1] == chat_id]:
            del self._items[key]
