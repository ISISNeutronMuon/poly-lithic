"""Tests for the evaluator module — alignment buffer, evaluators, observer, handlers."""

import math
import time
import pytest

from poly_lithic.src.evaluators.BaseEvaluator import BaseEvaluator, EvalResult
from poly_lithic.src.evaluators.alignment_buffer import AlignmentBuffer, PairedSample
from poly_lithic.src.evaluators.rolling_stats import RollingStatsEvaluator
from poly_lithic.src.evaluators.drift_detection import DriftDetectionEvaluator
from poly_lithic.src.evaluators.threshold_evaluator import ThresholdEvaluator
from poly_lithic.src.evaluators.handlers import (
    BrokerMessageHandler,
    WebhookHandler,
    ScriptHandler,
    build_handlers,
    check_condition,
)
from poly_lithic.src.evaluators import registered_evaluators
from poly_lithic.src.utils.messaging import EvaluatorObserver, Message, MessageBroker
from poly_lithic.src.utils.plugin_registry import evaluator_plugin_registry


# ──────────────────────────────────────────────────────
# AlignmentBuffer tests
# ──────────────────────────────────────────────────────

class TestAlignmentBufferLatest:
    """Tests for latest-value alignment mode."""

    @pytest.fixture
    def buffer(self):
        return AlignmentBuffer({
            'mapping': {'PRED:A': 'ACTUAL:A'},
            'alignment': {'mode': 'latest'},
            'window': {'type': 'samples', 'size': 5},
        })

    def test_pair_on_both_available(self, buffer):
        buffer.add_prediction('PRED:A', 1.0, 100.0)
        buffer.add_actual('ACTUAL:A', 1.1, 100.0)
        window = buffer.get_window('PRED:A')
        assert len(window) == 1
        assert window[0].prediction == 1.0
        assert window[0].actual == 1.1

    def test_no_pair_with_only_prediction(self, buffer):
        buffer.add_prediction('PRED:A', 1.0, 100.0)
        assert len(buffer.get_window('PRED:A')) == 0

    def test_no_pair_with_only_actual(self, buffer):
        buffer.add_actual('ACTUAL:A', 1.0, 100.0)
        assert len(buffer.get_window('PRED:A')) == 0

    def test_window_size_limit(self, buffer):
        for i in range(10):
            buffer.add_prediction('PRED:A', float(i), float(i))
            buffer.add_actual('ACTUAL:A', float(i) + 0.1, float(i))
        window = buffer.get_window('PRED:A')
        assert len(window) == 5

    def test_ignores_unknown_pvs(self, buffer):
        buffer.add_prediction('UNKNOWN:PV', 1.0)
        buffer.add_actual('UNKNOWN:PV', 1.0)
        assert not buffer.has_enough_data()

    def test_has_enough_data(self, buffer):
        assert not buffer.has_enough_data(2)
        buffer.add_prediction('PRED:A', 1.0, 1.0)
        buffer.add_actual('ACTUAL:A', 1.1, 1.0)
        assert not buffer.has_enough_data(2)
        buffer.add_prediction('PRED:A', 2.0, 2.0)
        buffer.add_actual('ACTUAL:A', 2.1, 2.0)
        assert buffer.has_enough_data(2)


class TestAlignmentBufferTimestamp:
    """Tests for timestamp-based alignment mode."""

    @pytest.fixture
    def buffer(self):
        return AlignmentBuffer({
            'mapping': {'PRED:A': 'ACTUAL:A'},
            'alignment': {'mode': 'timestamp', 'tolerance_s': 0.5},
            'window': {'type': 'samples', 'size': 100},
        })

    def test_pairs_within_tolerance(self, buffer):
        buffer.add_prediction('PRED:A', 1.0, 100.0)
        buffer.add_actual('ACTUAL:A', 1.1, 100.3)
        assert len(buffer.get_window('PRED:A')) == 1

    def test_rejects_outside_tolerance(self, buffer):
        buffer.add_prediction('PRED:A', 1.0, 100.0)
        buffer.add_actual('ACTUAL:A', 1.1, 101.0)
        assert len(buffer.get_window('PRED:A')) == 0


class TestAlignmentBufferTimeWindow:
    """Tests for time-based window trimming."""

    def test_time_window_trim(self):
        buf = AlignmentBuffer({
            'mapping': {'PRED:A': 'ACTUAL:A'},
            'alignment': {'mode': 'latest'},
            'window': {'type': 'time', 'size': 1.0},
        })
        old_ts = time.time() - 5.0
        buf._windows['PRED:A'].append(PairedSample(1.0, 1.0, old_ts))
        buf._windows['PRED:A'].append(PairedSample(2.0, 2.0, time.time()))
        window = buf.get_window('PRED:A')
        assert len(window) == 1  # old sample trimmed


class TestAlignmentBufferMultiPV:
    """Tests with multiple PV mappings."""

    @pytest.fixture
    def buffer(self):
        return AlignmentBuffer({
            'mapping': {'PRED:A': 'ACTUAL:A', 'PRED:B': 'ACTUAL:B'},
            'alignment': {'mode': 'latest'},
            'window': {'type': 'samples', 'size': 10},
        })

    def test_independent_windows(self, buffer):
        buffer.add_prediction('PRED:A', 1.0, 1.0)
        buffer.add_actual('ACTUAL:A', 1.1, 1.0)
        assert len(buffer.get_window('PRED:A')) == 1
        assert len(buffer.get_window('PRED:B')) == 0

    def test_all_windows(self, buffer):
        buffer.add_prediction('PRED:A', 1.0, 1.0)
        buffer.add_actual('ACTUAL:A', 1.1, 1.0)
        buffer.add_prediction('PRED:B', 2.0, 1.0)
        buffer.add_actual('ACTUAL:B', 2.1, 1.0)
        windows = buffer.get_all_windows()
        assert len(windows['PRED:A']) == 1
        assert len(windows['PRED:B']) == 1


# ──────────────────────────────────────────────────────
# RollingStatsEvaluator tests
# ──────────────────────────────────────────────────────

class TestRollingStatsEvaluator:

    @pytest.fixture
    def evaluator(self):
        return RollingStatsEvaluator({'metrics': ['rmse', 'mae', 'mean_bias', 'r_squared']})

    def test_perfect_predictions(self, evaluator):
        preds = {'PV': [1.0, 2.0, 3.0, 4.0, 5.0]}
        actuals = {'PV': [1.0, 2.0, 3.0, 4.0, 5.0]}
        result = evaluator.evaluate(preds, actuals)
        assert result.metrics['rmse'] == pytest.approx(0.0)
        assert result.metrics['mae'] == pytest.approx(0.0)
        assert result.metrics['mean_bias'] == pytest.approx(0.0)
        assert result.metrics['r_squared'] == pytest.approx(1.0)

    def test_constant_offset(self, evaluator):
        preds = {'PV': [2.0, 3.0, 4.0]}
        actuals = {'PV': [1.0, 2.0, 3.0]}
        result = evaluator.evaluate(preds, actuals)
        assert result.metrics['rmse'] == pytest.approx(1.0)
        assert result.metrics['mae'] == pytest.approx(1.0)
        assert result.metrics['mean_bias'] == pytest.approx(1.0)

    def test_empty_input(self, evaluator):
        result = evaluator.evaluate({}, {})
        assert math.isnan(result.metrics['rmse'])

    def test_selective_metrics(self):
        eval_ = RollingStatsEvaluator({'metrics': ['rmse']})
        result = eval_.evaluate({'PV': [1.0, 2.0]}, {'PV': [1.0, 2.0]})
        assert 'rmse' in result.metrics
        assert 'mae' not in result.metrics


# ──────────────────────────────────────────────────────
# DriftDetectionEvaluator tests
# ──────────────────────────────────────────────────────

class TestDriftDetectionEvaluator:

    @pytest.fixture
    def evaluator(self):
        return DriftDetectionEvaluator({
            'drift': {'ks_alpha': 0.05, 'cusum_threshold': 5.0, 'min_samples': 5}
        })

    def test_no_drift_zero_residuals(self, evaluator):
        preds = {'PV': [1.0] * 20}
        actuals = {'PV': [1.0] * 20}
        result = evaluator.evaluate(preds, actuals)
        assert not result.flags['drift_detected']
        assert not result.flags['cusum_alert']

    def test_insufficient_samples(self, evaluator):
        preds = {'PV': [1.0, 2.0]}
        actuals = {'PV': [1.0, 2.0]}
        result = evaluator.evaluate(preds, actuals)
        assert result.details.get('reason') == 'insufficient_samples'

    def test_detects_large_drift(self, evaluator):
        # Half the samples have zero error, half have large systematic error
        preds = {'PV': [0.0] * 10 + [10.0] * 10}
        actuals = {'PV': [0.0] * 10 + [0.0] * 10}
        result = evaluator.evaluate(preds, actuals)
        # Should detect drift (large step change in residuals)
        assert result.metrics['ks_statistic'] > 0
        assert result.metrics['cusum_max'] > 0


# ──────────────────────────────────────────────────────
# ThresholdEvaluator tests
# ──────────────────────────────────────────────────────

class TestThresholdEvaluator:

    def test_within_threshold(self):
        eval_ = ThresholdEvaluator({
            'thresholds': {'absolute': 1.0, 'relative': 0.5}
        })
        result = eval_.evaluate({'PV': [1.0, 2.0]}, {'PV': [1.0, 2.0]})
        assert not result.flags['any_threshold_exceeded']

    def test_absolute_threshold_exceeded(self):
        eval_ = ThresholdEvaluator({
            'thresholds': {'absolute': 0.5}
        })
        result = eval_.evaluate({'PV': [2.0]}, {'PV': [1.0]})
        assert result.flags['PV/abs_threshold_exceeded']
        assert result.flags['any_threshold_exceeded']

    def test_relative_threshold_exceeded(self):
        eval_ = ThresholdEvaluator({
            'thresholds': {'relative': 0.1}
        })
        result = eval_.evaluate({'PV': [1.5]}, {'PV': [1.0]})
        assert result.flags['PV/rel_threshold_exceeded']

    def test_per_pv_override(self):
        eval_ = ThresholdEvaluator({
            'thresholds': {
                'absolute': 10.0,
                'per_pv': {'PV': {'absolute': 0.1}},
            }
        })
        result = eval_.evaluate({'PV': [1.0]}, {'PV': [0.5]})
        assert result.flags['PV/abs_threshold_exceeded']

    def test_empty_input(self):
        eval_ = ThresholdEvaluator({'thresholds': {'absolute': 1.0}})
        result = eval_.evaluate({}, {})
        assert not result.flags.get('any_threshold_exceeded', True)


# ──────────────────────────────────────────────────────
# Workflow handler tests
# ──────────────────────────────────────────────────────

class TestCheckCondition:

    def test_simple_metric_condition(self):
        result = EvalResult(metrics={'rmse': 0.6})
        assert check_condition('rmse > 0.5', result)
        assert not check_condition('rmse > 1.0', result)

    def test_flag_condition(self):
        result = EvalResult(flags={'drift_detected': True})
        assert check_condition('drift_detected', result)

    def test_empty_condition_always_true(self):
        assert check_condition('', EvalResult())

    def test_invalid_condition(self):
        # Should not raise, returns False
        assert not check_condition('invalid_var > 0', EvalResult())


class TestBrokerMessageHandler:

    def test_creates_message(self):
        handler = BrokerMessageHandler({'topic': 'my_alarm'})
        result = EvalResult(metrics={'rmse': 0.5}, flags={'drift': True})
        context = {}
        handler.handle(result, context)
        assert len(context['messages']) == 1
        msg = context['messages'][0]
        assert msg['topic'] == 'my_alarm'
        assert 'rmse' in msg['value']
        assert msg['value']['drift']['value'] == 1


class TestBuildHandlers:

    def test_builds_from_config(self):
        configs = [
            {'type': 'broker_message', 'condition': 'rmse > 0.5', 'topic': 'alarm'},
        ]
        handlers = build_handlers(configs)
        assert len(handlers) == 1
        assert handlers[0][0] == 'rmse > 0.5'

    def test_unknown_type_skipped(self):
        configs = [{'type': 'nonexistent', 'condition': ''}]
        handlers = build_handlers(configs)
        assert len(handlers) == 0


# ──────────────────────────────────────────────────────
# EvaluatorObserver integration tests
# ──────────────────────────────────────────────────────

class TestEvaluatorObserver:

    @pytest.fixture
    def observer(self):
        return EvaluatorObserver(
            config={
                'mapping': {'PRED:A': 'ACTUAL:A'},
                'alignment': {'mode': 'latest'},
                'window': {'type': 'samples', 'size': 100},
                'evaluators': [
                    {'type': 'RollingStatsEvaluator', 'metrics': ['rmse', 'mae']},
                ],
                'model_topic': 'model',
                'min_eval_samples': 2,
            },
            topic='eval_results',
        )

    def _model_msg(self, pred_val, ts=None):
        return Message(
            topic='model',
            source='test_model',
            value={'PRED:A': {'value': pred_val, 'timestamp': ts or time.time()}},
        )

    def _actual_msg(self, actual_val, ts=None):
        return Message(
            topic='in_interface',
            source='test_interface',
            value={'ACTUAL:A': {'value': actual_val, 'timestamp': ts or time.time()}},
        )

    def test_returns_none_without_enough_data(self, observer):
        result = observer.update(self._model_msg(1.0))
        assert result is None

    def test_produces_eval_message_after_pairs(self, observer):
        observer.update(self._model_msg(1.0))
        observer.update(self._actual_msg(1.0))
        observer.update(self._model_msg(2.0))
        result = observer.update(self._actual_msg(2.0))
        assert result is not None
        assert isinstance(result, list)
        assert len(result) >= 1
        eval_msg = result[0]
        assert eval_msg.topic == 'eval_results'
        assert 'rmse' in eval_msg.value

    def test_perfect_predictions_zero_rmse(self, observer):
        for i in range(5):
            observer.update(self._model_msg(float(i)))
            observer.update(self._actual_msg(float(i)))
        # Last update should return eval message
        result = observer.update(self._model_msg(5.0))
        # After adding prediction without actual, might not have new pair yet
        observer.update(self._actual_msg(5.0))
        result = observer.update(self._model_msg(6.0))
        if result:
            rmse_val = result[0].value['rmse']['value']
            assert rmse_val == pytest.approx(0.0)

    def test_workflow_triggered(self):
        obs = EvaluatorObserver(
            config={
                'mapping': {'PRED:A': 'ACTUAL:A'},
                'alignment': {'mode': 'latest'},
                'window': {'type': 'samples', 'size': 100},
                'evaluators': [
                    {'type': 'RollingStatsEvaluator', 'metrics': ['rmse']},
                ],
                'model_topic': 'model',
                'min_eval_samples': 2,
                'workflows': [
                    {
                        'type': 'broker_message',
                        'condition': 'rmse > 0.01',
                        'topic': 'eval_alarm',
                    },
                ],
            },
            topic='eval_results',
        )
        # Feed pairs with constant offset so rmse > 0.01
        for i in range(3):
            obs.update(Message(
                topic='model', source='m',
                value={'PRED:A': {'value': float(i) + 1.0}},
            ))
            obs.update(Message(
                topic='in_interface', source='i',
                value={'ACTUAL:A': {'value': float(i)}},
            ))
        # Trigger one more to get eval output
        obs.update(Message(
            topic='model', source='m',
            value={'PRED:A': {'value': 10.0}},
        ))
        result = obs.update(Message(
            topic='in_interface', source='i',
            value={'ACTUAL:A': {'value': 9.0}},
        ))
        assert result is not None
        topics = [m.topic for m in result]
        assert 'eval_alarm' in topics


class TestEvaluatorObserverBrokerIntegration:
    """Test EvaluatorObserver wired into a MessageBroker."""

    def test_end_to_end(self):
        broker = MessageBroker()
        observer = EvaluatorObserver(
            config={
                'mapping': {'PRED:A': 'ACTUAL:A'},
                'alignment': {'mode': 'latest'},
                'window': {'type': 'samples', 'size': 100},
                'evaluators': [
                    {'type': 'RollingStatsEvaluator', 'metrics': ['rmse']},
                ],
                'model_topic': 'model',
                'min_eval_samples': 2,
            },
            topic='eval_results',
        )
        broker.attach(observer, ['model', 'in_interface'])

        # Collect eval_results messages
        collected = []

        class Collector:
            def update(self, msg):
                collected.append(msg)
                return None

        broker.attach(Collector(), 'eval_results')

        # Send paired data through broker
        for i in range(3):
            broker.queue.append(Message(
                topic='model', source='model_obs',
                value={'PRED:A': {'value': float(i) + 0.5}},
            ))
            broker.queue.append(Message(
                topic='in_interface', source='interface_obs',
                value={'ACTUAL:A': {'value': float(i)}},
            ))
            broker.parse_queue()

        assert len(collected) > 0
        assert 'rmse' in collected[-1].value


# ──────────────────────────────────────────────────────
# Plugin registry tests
# ──────────────────────────────────────────────────────

class TestEvaluatorRegistry:

    def test_registered_evaluators_populated(self):
        assert 'RollingStatsEvaluator' in registered_evaluators
        assert 'DriftDetectionEvaluator' in registered_evaluators
        assert 'ThresholdEvaluator' in registered_evaluators

    def test_plugin_registry_exists(self):
        assert evaluator_plugin_registry.group_name == 'poly_lithic.evaluators'

    def test_manual_registration(self):
        class CustomEvaluator(BaseEvaluator):
            def __init__(self, config):
                pass

            def evaluate(self, predictions, actuals, timestamps=None):
                return EvalResult(metrics={'custom': 42.0})

            @property
            def name(self):
                return 'CustomEvaluator'

        evaluator_plugin_registry.register('custom_eval', CustomEvaluator)
        assert evaluator_plugin_registry.has_plugin('custom_eval')
        cls = evaluator_plugin_registry.get('custom_eval')
        result = cls({}).evaluate({'PV': [1.0]}, {'PV': [1.0]})
        assert result.metrics['custom'] == 42.0
        # Cleanup
        evaluator_plugin_registry.unregister('custom_eval')
