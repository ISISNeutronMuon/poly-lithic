"""Tests for EvaluatorObserver edge cases: workflow cooldown, non-scalar
values, and data-clock time windows in AlignmentBuffer."""

import logging

import numpy as np
import pytest

import poly_lithic.src.utils.messaging as messaging
from poly_lithic.src.evaluators.alignment_buffer import AlignmentBuffer
from poly_lithic.src.utils.messaging import EvaluatorObserver, Message


def _make_observer(workflows=None, mapping=None, window=None):
    return EvaluatorObserver(
        config={
            'mapping': mapping or {'PRED:A': 'ACTUAL:A'},
            'alignment': {'mode': 'latest'},
            'window': window or {'type': 'samples', 'size': 100},
            'evaluators': [
                {'type': 'RollingStatsEvaluator', 'metrics': ['rmse']},
            ],
            'model_topic': 'model',
            'min_eval_samples': 2,
            'workflows': workflows or [],
        },
        topic='eval_results',
    )


def _feed_pair(obs, pred, actual, ts=None):
    """Feed one prediction + actual; return messages from both updates.

    Only the update that completes a new pair can trigger evaluation.
    """
    pred_struct = {'value': pred}
    actual_struct = {'value': actual}
    if ts is not None:
        pred_struct['timestamp'] = ts
        actual_struct['timestamp'] = ts
    r1 = obs.update(Message(topic='model', source='m', value={'PRED:A': pred_struct}))
    r2 = obs.update(Message(topic='gt', source='i', value={'ACTUAL:A': actual_struct}))
    return (r1 or []) + (r2 or [])


def _topics(result):
    return [m.topic for m in (result or [])]


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = FakeClock()
    monkeypatch.setattr(messaging.time, 'monotonic', c)
    return c


# ──────────────────────────────────────────────────────
# Workflow cooldown
# ──────────────────────────────────────────────────────

class TestWorkflowCooldown:

    def test_default_cooldown_fires_every_time(self, clock):
        obs = _make_observer(workflows=[
            {'type': 'broker_message', 'condition': 'rmse > 0.01', 'topic': 'alarm'},
        ])
        _feed_pair(obs, 1.0, 0.0)
        for _ in range(3):
            assert 'alarm' in _topics(_feed_pair(obs, 1.0, 0.0))

    def test_cooldown_suppresses_then_refires(self, clock):
        obs = _make_observer(workflows=[
            {'type': 'broker_message', 'condition': 'rmse > 0.01',
             'topic': 'alarm', 'cooldown_s': 10},
        ])
        _feed_pair(obs, 1.0, 0.0)
        assert 'alarm' in _topics(_feed_pair(obs, 1.0, 0.0))

        # Within cooldown: eval message still published, workflow suppressed
        clock.t += 5
        result = _feed_pair(obs, 1.0, 0.0)
        assert 'eval_results' in _topics(result)
        assert 'alarm' not in _topics(result)

        # After cooldown: fires again
        clock.t += 6
        assert 'alarm' in _topics(_feed_pair(obs, 1.0, 0.0))
        # And cooldown restarts from the new fire
        clock.t += 1
        assert 'alarm' not in _topics(_feed_pair(obs, 1.0, 0.0))

    def test_cooldown_aligned_with_unknown_handler_type(self, clock):
        obs = _make_observer(workflows=[
            {'type': 'does_not_exist', 'condition': 'rmse > 0.01', 'cooldown_s': 1000},
            {'type': 'broker_message', 'condition': 'rmse > 0.01', 'topic': 'no_cd'},
            {'type': 'broker_message', 'condition': 'rmse > 0.01',
             'topic': 'with_cd', 'cooldown_s': 10},
        ])
        assert len(obs._workflows) == 2
        assert [cd for _, _, cd in obs._workflows] == [0.0, 10.0]

        _feed_pair(obs, 1.0, 0.0)
        first = _topics(_feed_pair(obs, 1.0, 0.0))
        assert 'no_cd' in first and 'with_cd' in first

        clock.t += 1
        second = _topics(_feed_pair(obs, 1.0, 0.0))
        # The unknown entry's 1000s cooldown must not leak onto 'no_cd'
        assert 'no_cd' in second
        assert 'with_cd' not in second

    def test_failing_handler_does_not_block_others(self, clock):
        obs = _make_observer(workflows=[
            {'type': 'broker_message', 'condition': 'rmse > 0.01', 'topic': 'a'},
            {'type': 'broker_message', 'condition': 'rmse > 0.01', 'topic': 'b'},
        ])

        def boom(*args, **kwargs):
            raise RuntimeError('boom')

        obs._workflows[0][1].handle = boom
        _feed_pair(obs, 1.0, 0.0)
        result = _topics(_feed_pair(obs, 1.0, 0.0))
        assert 'b' in result
        assert 'eval_results' in result


# ──────────────────────────────────────────────────────
# Non-scalar values
# ──────────────────────────────────────────────────────

class TestNonScalarValues:

    MAPPING = {'PRED:A': 'ACTUAL:A', 'PRED:W': 'ACTUAL:W'}

    @pytest.mark.parametrize('bad', [
        [1.0, 2.0],
        np.array([1.0, 2.0, 3.0]),
        'not a number',
        '1.5',
        None,
        {'nested': 1},
    ])
    def test_bad_values_skipped_scalar_still_processed(self, bad):
        obs = _make_observer(mapping=self.MAPPING)
        for i in range(3):
            obs.update(Message(topic='model', source='m', value={
                'PRED:W': {'value': bad},
                'PRED:A': {'value': float(i) + 1.0},
            }))
            result = obs.update(Message(topic='gt', source='i', value={
                'ACTUAL:W': {'value': bad},
                'ACTUAL:A': {'value': float(i)},
            }))
        assert len(obs.buffer.get_window('PRED:A')) == 3
        assert obs.buffer.get_window('PRED:W') == []
        assert 'eval_results' in _topics(result)

    def test_numpy_scalars_and_0d_arrays_accepted(self):
        obs = _make_observer()
        obs.update(Message(topic='model', source='m',
                           value={'PRED:A': {'value': np.float32(1.5)}}))
        obs.update(Message(topic='gt', source='i',
                           value={'ACTUAL:A': {'value': np.array(1.0)}}))
        obs.update(Message(topic='model', source='m',
                           value={'PRED:A': {'value': np.int64(2)}}))
        obs.update(Message(topic='gt', source='i',
                           value={'ACTUAL:A': {'value': 2}}))
        window = obs.buffer.get_window('PRED:A')
        assert [(s.prediction, s.actual) for s in window] == [(1.5, 1.0), (2.0, 2.0)]
        assert all(isinstance(s.prediction, float) for s in window)

    def test_warns_once_per_pv(self, caplog):
        obs = _make_observer()
        with caplog.at_level(logging.DEBUG):
            for _ in range(5):
                obs.update(Message(topic='model', source='m',
                                   value={'PRED:A': {'value': [1, 2]}}))
        warnings = [r for r in caplog.records
                    if r.levelno == logging.WARNING and 'PRED:A' in r.getMessage()]
        assert len(warnings) <= 1  # logger may not propagate to caplog
        assert obs._nonscalar_warned == {'PRED:A'}

    def test_unmapped_nonscalar_pv_ignored_silently(self):
        obs = _make_observer()
        obs.update(Message(topic='model', source='m',
                           value={'OTHER:WAVE': {'value': [1, 2, 3]}}))
        assert obs._nonscalar_warned == set()


# ──────────────────────────────────────────────────────
# Time windows on the data clock
# ──────────────────────────────────────────────────────

class TestTimeWindowDataClock:

    def _buffer(self, size=10.0):
        return AlignmentBuffer({
            'mapping': {'P': 'A'},
            'alignment': {'mode': 'latest'},
            'window': {'type': 'time', 'size': size},
        })

    def test_old_timestamps_kept(self):
        buf = self._buffer()
        for ts in (1000.0, 1001.0, 1002.0):
            buf.add_prediction('P', 1.0, ts)
            buf.add_actual('A', 1.0, ts)
        # Wall-clock is ~1.7e9; with wall-clock trimming all would be dropped
        assert len(buf.get_window('P')) == 3
        assert buf.has_enough_data(2)

    def test_trims_relative_to_newest(self):
        buf = self._buffer(size=10.0)
        for ts in (1000.0, 1005.0, 1011.0, 1015.0):
            buf.add_prediction('P', 1.0, ts)
            buf.add_actual('A', 1.0, ts)
        # Newest is 1015 -> cutoff 1005; 1000 dropped, 1005 kept (boundary)
        assert [s.timestamp for s in buf.get_window('P')] == [1005.0, 1011.0, 1015.0]

    def test_future_timestamps_kept(self):
        buf = self._buffer(size=10.0)
        base = 1e10  # far in the future relative to wall-clock
        for i in range(3):
            buf.add_prediction('P', 1.0, base + i)
            buf.add_actual('A', 1.0, base + i)
        assert len(buf.get_window('P')) == 3

    def test_observer_time_window_with_offset_clock(self):
        obs = _make_observer(window={'type': 'time', 'size': 10.0})
        result = None
        for i in range(4):
            result = _feed_pair(obs, float(i) + 1.0, float(i), ts=1000.0 + i)
        assert len(obs.buffer.get_window('PRED:A')) == 4
        assert 'eval_results' in _topics(result)


class TestEvaluateOnNewPairOnly:
    def test_unpaired_update_does_not_republish(self):
        obs = _make_observer()
        _feed_pair(obs, 1.0, 1.1)
        assert _topics(_feed_pair(obs, 2.0, 2.2)) == ['eval_results']

        # Ground truth with no waiting prediction pairs nothing
        r = obs.update(Message(topic='gt', source='i', value={'ACTUAL:A': {'value': 2.3}}))
        assert r is None
        # Neither does a newer actual replacing the unpaired one
        r = obs.update(Message(topic='gt', source='i', value={'ACTUAL:A': {'value': 2.4}}))
        assert r is None

    def test_new_pair_publishes_once(self):
        obs = _make_observer()
        _feed_pair(obs, 1.0, 1.1)
        r1 = obs.update(Message(topic='model', source='m', value={'PRED:A': {'value': 2.0}}))
        r2 = obs.update(Message(topic='gt', source='i', value={'ACTUAL:A': {'value': 2.2}}))
        assert r1 is None
        assert _topics(r2) == ['eval_results']
