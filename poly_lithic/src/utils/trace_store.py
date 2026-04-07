"""In-memory ring buffer for message trace records."""

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


def _serialise_value(v: Any) -> Any:
    """Convert a value to something JSON-safe."""
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, dict):
        return {k: _serialise_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_serialise_value(i) for i in v]
    # Handle p4p scalar wrappers (ntfloat, ntint, etc.) which are float/int
    # subclasses but contain unpicklable C-level state.
    if isinstance(v, float):
        return float(v)
    if isinstance(v, int) and not isinstance(v, bool):
        return int(v)
    return v


@dataclass
class TraceRecord:
    trace_id: str
    parent_trace_ids: list[str]
    topic: str
    source: str
    timestamp: float
    variable_keys: list[str] = field(default_factory=list)
    variable_values: dict[str, Any] = field(default_factory=dict)


class TraceStore:
    """Thread-safe in-memory ring buffer of TraceRecords."""

    def __init__(self, maxlen: int = 10000):
        self._buffer: collections.deque[TraceRecord] = collections.deque(maxlen=maxlen)
        self._index: dict[str, TraceRecord] = {}
        self._lock = threading.Lock()
        self._maxlen = maxlen

    def record(self, message) -> None:
        """Record a message as a TraceRecord."""
        vals = {}
        if isinstance(message.value, dict):
            for k, v in message.value.items():
                if isinstance(v, dict) and 'value' in v:
                    vals[k] = _serialise_value(v['value'])
                else:
                    vals[k] = _serialise_value(v)
        rec = TraceRecord(
            trace_id=message.trace_id,
            parent_trace_ids=list(message.parent_trace_ids),
            topic=message.topic,
            source=message.source,
            timestamp=time.time(),
            variable_keys=list(message.value.keys()) if isinstance(message.value, dict) else [],
            variable_values=vals,
        )
        with self._lock:
            # If buffer is full, the evicted record should be removed from index
            if len(self._buffer) == self._maxlen:
                evicted = self._buffer[0]
                self._index.pop(evicted.trace_id, None)
            self._buffer.append(rec)
            self._index[rec.trace_id] = rec

    def get(self, trace_id: str) -> TraceRecord | None:
        """Get a single trace record by ID."""
        with self._lock:
            return self._index.get(trace_id)

    def get_lineage(self, trace_id: str) -> list[TraceRecord]:
        """Walk parent_trace_ids to build the full ancestry chain."""
        with self._lock:
            result = []
            visited = set()
            queue = [trace_id]
            while queue:
                tid = queue.pop(0)
                if tid in visited:
                    continue
                visited.add(tid)
                rec = self._index.get(tid)
                if rec is not None:
                    result.append(rec)
                    for pid in rec.parent_trace_ids:
                        if pid not in visited:
                            queue.append(pid)
            return result

    def get_recent(self, limit: int = 100) -> list[TraceRecord]:
        """Return the most recent trace records."""
        with self._lock:
            items = list(self._buffer)
            return items[-limit:]
