"""Tests for evaluator workflow handlers — condition parsing and JSON payloads."""

import json
import math
import sys

import pytest

from poly_lithic.src.evaluators.BaseEvaluator import EvalResult
from poly_lithic.src.evaluators.handlers import (
    PVAlarmHandler,
    ScriptHandler,
    _json_safe,
    build_json_payload,
    check_condition,
)


def _strict_loads(text: str):
    def _reject(token):
        raise ValueError(f'non-standard JSON constant: {token}')

    return json.loads(text, parse_constant=_reject)


class TestLogicalOperators:
    def test_and_with_flag(self):
        r = EvalResult(metrics={'mae': 0.5}, flags={'drift_detected': True})
        assert check_condition('mae > 0.1 and drift_detected', r)
        r2 = EvalResult(metrics={'mae': 0.5}, flags={'drift_detected': False})
        assert not check_condition('mae > 0.1 and drift_detected', r2)

    def test_and_precedence_comparisons(self):
        r = EvalResult(metrics={'a': 5, 'b': 1})
        assert check_condition('a > 1 and b < 2', r)
        assert not check_condition('a > 1 and b > 2', r)
        assert not check_condition('a < 1 and b < 2', r)

    def test_or(self):
        r = EvalResult(metrics={'a': 0, 'b': 3})
        assert check_condition('a > 1 or b > 2', r)
        assert not check_condition('a > 1 or b > 5', r)

    def test_not(self):
        r = EvalResult(metrics={'rmse': 0.1}, flags={'drift_detected': False})
        assert check_condition('not drift_detected', r)
        assert check_condition('not drift_detected and rmse < 0.2', r)
        assert not check_condition('not (rmse < 0.2)', r)

    def test_and_binds_tighter_than_or(self):
        r = EvalResult(metrics={'a': 1, 'b': 0, 'c': 0})
        # a or (b and c) -> True ; (a or b) and c -> False
        assert check_condition('a > 0 or b > 0 and c > 0', r)
        assert not check_condition('(a > 0 or b > 0) and c > 0', r)

    def test_keyword_inside_name_not_mangled(self):
        r = EvalResult(metrics={'android_score': 2, 'notional': 3})
        assert check_condition('android_score > 1 and notional > 2', r)

    def test_sympy_style_operators_still_work(self):
        r = EvalResult(metrics={'mae': 0.5}, flags={'drift_detected': True})
        assert check_condition('(mae > 0.1) & drift_detected', r)
        assert check_condition('(mae > 1) | drift_detected', r)
        assert not check_condition('~drift_detected', r)

    def test_arithmetic_and_chained_comparison(self):
        r = EvalResult(metrics={'rmse': 0.3, 'mae': 0.1})
        assert check_condition('0.1 < rmse < 0.5', r)
        assert check_condition('rmse - mae >= 0.2 - 1e-9', r)
        assert check_condition('rmse / mae > 2', r)


class TestPVNames:
    def test_pv_metric(self):
        r = EvalResult(metrics={'ML:PRED:TEMP/max_abs_error': 2.5})
        assert check_condition('ML:PRED:TEMP/max_abs_error > 1', r)
        assert not check_condition('ML:PRED:TEMP/max_abs_error > 3', r)

    def test_pv_flag(self):
        r = EvalResult(flags={'ML:PRED:TEMP/abs_threshold_exceeded': True})
        assert check_condition('ML:PRED:TEMP/abs_threshold_exceeded', r)
        assert not check_condition('not ML:PRED:TEMP/abs_threshold_exceeded', r)

    def test_pv_names_with_dots_combined(self):
        r = EvalResult(
            metrics={'ml.pred.temp/max_abs_error': 2.0},
            flags={'ML:PRED:TEMP/abs_threshold_exceeded': True},
        )
        assert check_condition(
            'ml.pred.temp/max_abs_error > 1 and ML:PRED:TEMP/abs_threshold_exceeded',
            r,
        )

    def test_substring_overlapping_names(self):
        r = EvalResult(
            metrics={
                'ML:PRED:TEMP': 100.0,
                'ML:PRED:TEMP/max_abs_error': 0.5,
                'rmse': 1.0,
                'rmse_ratio': 0.1,
            }
        )
        assert check_condition('ML:PRED:TEMP/max_abs_error < 1', r)
        assert check_condition('ML:PRED:TEMP > 50', r)
        assert check_condition('rmse_ratio < 0.5 and rmse > 0.5', r)
        assert not check_condition('rmse_ratio > 0.5', r)

    def test_plain_names_still_work(self):
        r = EvalResult(metrics={'rmse': 0.6}, flags={'drift_detected': True})
        assert check_condition('rmse > 0.5', r)
        assert check_condition('drift_detected', r)


class TestEdgeCases:
    def test_unknown_variable_returns_false(self, caplog):
        r = EvalResult(metrics={'rmse': 0.6})
        with caplog.at_level('WARNING'):
            assert not check_condition('unknown_var > 0', r)
        assert 'unknown' in caplog.text.lower()

    def test_unknown_variable_in_or_branch(self):
        r = EvalResult(metrics={'rmse': 0.6})
        assert not check_condition('rmse < 0.1 or missing > 0', r)
        # validated up front, so short-circuiting doesn't hide it
        assert not check_condition('rmse > 0.1 or missing > 0', r)

    def test_empty_condition_true(self):
        assert check_condition('', EvalResult())
        assert check_condition('   ', EvalResult())

    def test_unsafe_syntax_rejected(self):
        r = EvalResult(metrics={'rmse': 0.6})
        assert not check_condition('__import__("os").system("true")', r)
        assert not check_condition('rmse.__class__', r)
        assert not check_condition('[rmse][0] > 0', r)

    def test_nan_metric_comparison_false(self):
        r = EvalResult(metrics={'rmse': float('nan')})
        assert not check_condition('rmse > 0', r)


class TestJsonPayload:
    def test_json_safe_recursive(self):
        data = {
            'a': float('inf'),
            'b': [1.0, float('nan'), {'c': -float('inf')}],
            'd': (2.0, float('nan')),
            'e': 'text',
            'f': True,
        }
        out = _json_safe(data)
        assert out == {'a': None, 'b': [1.0, None, {'c': None}], 'd': [2.0, None],
                       'e': 'text', 'f': True}

    def test_json_safe_numpy(self):
        np = pytest.importorskip('numpy')
        out = _json_safe({'x': np.float64('inf'), 'y': np.array([1.0, np.nan])})
        assert out == {'x': None, 'y': [1.0, None]}

    def test_build_json_payload_strict(self):
        r = EvalResult(
            metrics={'ML:PRED:TEMP/max_abs_error': float('inf'), 'rmse': float('nan')},
            flags={'drift_detected': True},
            details={'window': [1.0, float('nan')]},
        )
        payload = _strict_loads(build_json_payload(r))
        assert payload['metrics'] == {'ML:PRED:TEMP/max_abs_error': None, 'rmse': None}
        assert payload['flags'] == {'drift_detected': True}
        assert payload['details'] == {'window': [1.0, None]}
        # original result untouched
        assert math.isinf(r.metrics['ML:PRED:TEMP/max_abs_error'])

    def test_script_handler_receives_strict_json(self, tmp_path):
        out_file = tmp_path / 'payload.json'
        script = tmp_path / 'check.py'
        script.write_text(
            'import json, sys\n'
            'def reject(t):\n'
            '    raise ValueError(t)\n'
            'data = json.load(sys.stdin, parse_constant=reject)\n'
            f'open({str(out_file)!r}, "w").write(json.dumps(data))\n'
        )
        handler = ScriptHandler({'command': f'"{sys.executable}" "{script}"'})
        r = EvalResult(
            metrics={'max_abs_error': float('inf'), 'mean': float('nan')},
            flags={'abs_threshold_exceeded': True},
        )
        handler.handle(r, {})
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data['metrics'] == {'max_abs_error': None, 'mean': None}
        assert data['flags'] == {'abs_threshold_exceeded': True}


class TestPVAlarmHandler:
    def test_default_value_is_one(self):
        handler = PVAlarmHandler({'pv': 'ML:ALARM'})
        context: dict = {}
        handler.handle(EvalResult(), context)
        assert context['messages'][0]['value']['ML:ALARM']['value'] == 1

    def test_clear_value(self):
        handler = PVAlarmHandler({'pv': 'ML:ALARM', 'value': 0, 'severity': 0})
        context: dict = {}
        handler.handle(EvalResult(), context)
        pv = context['messages'][0]['value']['ML:ALARM']
        assert pv['value'] == 0
        assert pv['alarm']['severity'] == 0
