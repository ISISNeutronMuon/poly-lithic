"""Alignment buffer that pairs model predictions with ground-truth values.

Supports two alignment modes:
- "latest": pairs the most recent prediction with the most recent actual
  (no timestamp matching).
- "timestamp": pairs predictions and actuals whose timestamps are within
  a configurable tolerance.

And two window types:
- "samples": keep the last N paired samples.
- "time": keep samples from the last T seconds.

Time-window semantics
---------------------
Time windows are measured on the *data clock*: the cutoff is
``newest_sample.timestamp - size`` for each window, where sample timestamps
come from the incoming messages (i.e. the data source's clock), not from the
local wall clock.  This makes the window robust to clock offsets between the
data source and the host running the evaluator.

Consequence: the window only advances when new paired samples arrive.  If a
data source stops updating, its window keeps the last T seconds of data it
did see (it is not emptied by wall-clock time passing).  Since evaluation is
only triggered by incoming messages, a stale window is re-evaluated only when
some other mapped PV produces data.

Samples without a timestamp fall back to ``time.time()``; mixing timestamped
and un-timestamped sources in one mapping therefore mixes clocks.
"""

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class PairedSample:
    prediction: float
    actual: float
    timestamp: float


class AlignmentBuffer:
    """Collects prediction and ground-truth values, pairs them, and
    maintains a rolling window of paired samples per PV mapping."""

    def __init__(self, config: dict):
        alignment_cfg = config.get('alignment', {})
        self.mode: str = alignment_cfg.get('mode', 'latest')
        self.tolerance_s: float = alignment_cfg.get('tolerance_s', 1.0)

        window_cfg = config.get('window', {})
        self.window_type: str = window_cfg.get('type', 'samples')
        self.window_size: int | float = window_cfg.get('size', 100)

        # Mapping: prediction_pv -> ground_truth_pv
        self.mapping: dict[str, str] = config.get('mapping', {})
        # Reverse mapping for look-up: ground_truth_pv -> prediction_pv
        self._reverse_map: dict[str, str] = {v: k for k, v in self.mapping.items()}

        # Latest un-paired values: {pv_name: (value, timestamp)}
        self._pred_latest: dict[str, tuple[float, float]] = {}
        self._actual_latest: dict[str, tuple[float, float]] = {}

        # Paired sample windows per prediction PV
        self._windows: dict[str, deque[PairedSample]] = {
            pred_pv: deque() for pred_pv in self.mapping
        }
        # Total pairs created since construction (lets callers detect new data)
        self.pair_count: int = 0

    def add_prediction(self, pv_name: str, value: float, timestamp: float | None = None):
        """Record a new prediction value."""
        if pv_name not in self.mapping:
            return
        ts = timestamp if timestamp is not None else time.time()
        self._pred_latest[pv_name] = (value, ts)
        self._try_pair(pv_name)

    def add_actual(self, pv_name: str, value: float, timestamp: float | None = None):
        """Record a new ground-truth value."""
        if pv_name not in self._reverse_map:
            return
        ts = timestamp if timestamp is not None else time.time()
        self._actual_latest[pv_name] = (value, ts)
        pred_pv = self._reverse_map[pv_name]
        self._try_pair(pred_pv)

    def _try_pair(self, pred_pv: str):
        """Attempt to create a paired sample for a prediction PV."""
        actual_pv = self.mapping[pred_pv]
        if pred_pv not in self._pred_latest or actual_pv not in self._actual_latest:
            return

        pred_val, pred_ts = self._pred_latest[pred_pv]
        actual_val, actual_ts = self._actual_latest[actual_pv]

        if self.mode == 'timestamp':
            if abs(pred_ts - actual_ts) > self.tolerance_s:
                return

        sample = PairedSample(
            prediction=pred_val,
            actual=actual_val,
            timestamp=max(pred_ts, actual_ts),
        )
        window = self._windows[pred_pv]
        window.append(sample)
        self.pair_count += 1

        # Clear latest to avoid re-pairing
        del self._pred_latest[pred_pv]
        del self._actual_latest[actual_pv]

        self._trim_window(pred_pv)

    def _trim_window(self, pred_pv: str):
        """Trim window to configured size."""
        window = self._windows[pred_pv]
        if self.window_type == 'samples':
            while len(window) > int(self.window_size):
                window.popleft()
        elif self.window_type == 'time':
            if not window:
                return
            # Data clock: cut off relative to the newest sample, not wall-clock
            newest_ts = max(s.timestamp for s in window)
            cutoff = newest_ts - float(self.window_size)
            while window and window[0].timestamp < cutoff:
                window.popleft()

    def get_window(self, pred_pv: str) -> list[PairedSample]:
        """Return the current paired-sample window for a prediction PV."""
        if self.window_type == 'time':
            self._trim_window(pred_pv)
        return list(self._windows.get(pred_pv, []))

    def get_all_windows(self) -> dict[str, list[PairedSample]]:
        """Return paired windows for all prediction PVs."""
        return {pv: self.get_window(pv) for pv in self.mapping}

    def has_enough_data(self, min_samples: int = 2) -> bool:
        """Check if any PV mapping has enough data to evaluate."""
        return any(
            len(self.get_window(pv)) >= min_samples for pv in self.mapping
        )

    @property
    def prediction_pvs(self) -> set[str]:
        return set(self.mapping.keys())

    @property
    def actual_pvs(self) -> set[str]:
        return set(self.mapping.values())

    @property
    def all_pvs(self) -> set[str]:
        return self.prediction_pvs | self.actual_pvs
