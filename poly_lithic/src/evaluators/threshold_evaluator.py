"""Threshold evaluator — absolute and relative error bounds per-PV."""

import math
from poly_lithic.src.evaluators.BaseEvaluator import BaseEvaluator, EvalResult


class ThresholdEvaluator(BaseEvaluator):
    """Checks whether prediction errors exceed configured thresholds.

    Config example::

        thresholds:
            absolute: 1.0          # max absolute error (all PVs)
            relative: 0.1          # max relative error (fraction)
            per_pv:
                ML:PRED:TEMP:
                    absolute: 0.5
                    relative: 0.05
    """

    def __init__(self, config: dict):
        self.config = config
        thresh_cfg = config.get('thresholds', {})
        self.abs_threshold: float | None = thresh_cfg.get('absolute', None)
        self.rel_threshold: float | None = thresh_cfg.get('relative', None)
        self.per_pv: dict[str, dict] = thresh_cfg.get('per_pv', {})

    @property
    def name(self) -> str:
        return 'ThresholdEvaluator'

    def evaluate(
        self,
        predictions: dict[str, list[float]],
        actuals: dict[str, list[float]],
        timestamps: list[float] | None = None,
    ) -> EvalResult:
        metrics: dict[str, float] = {}
        flags: dict[str, bool] = {}
        breaches: list[dict] = []

        any_breach = False

        for pv in predictions:
            preds = predictions[pv]
            acts = actuals.get(pv, [])
            n = min(len(preds), len(acts))
            if n == 0:
                continue

            # Get per-PV thresholds or fall back to global
            pv_cfg = self.per_pv.get(pv, {})
            abs_thresh = pv_cfg.get('absolute', self.abs_threshold)
            rel_thresh = pv_cfg.get('relative', self.rel_threshold)

            abs_errors = [abs(p - a) for p, a in zip(preds[:n], acts[:n])]
            max_abs = max(abs_errors)
            mean_abs = sum(abs_errors) / n
            metrics[f'{pv}/max_abs_error'] = max_abs
            metrics[f'{pv}/mean_abs_error'] = mean_abs

            if abs_thresh is not None:
                exceeded = max_abs > abs_thresh
                flags[f'{pv}/abs_threshold_exceeded'] = exceeded
                if exceeded:
                    any_breach = True
                    breaches.append({
                        'pv': pv,
                        'type': 'absolute',
                        'threshold': abs_thresh,
                        'value': max_abs,
                    })

            if rel_thresh is not None:
                rel_errors = [
                    abs(p - a) / abs(a) if abs(a) > 1e-12 else float('inf')
                    for p, a in zip(preds[:n], acts[:n])
                ]
                max_rel = max(rel_errors)
                metrics[f'{pv}/max_rel_error'] = max_rel
                exceeded = max_rel > rel_thresh
                flags[f'{pv}/rel_threshold_exceeded'] = exceeded
                if exceeded:
                    any_breach = True
                    breaches.append({
                        'pv': pv,
                        'type': 'relative',
                        'threshold': rel_thresh,
                        'value': max_rel,
                    })

        flags['any_threshold_exceeded'] = any_breach

        return EvalResult(
            metrics=metrics,
            flags=flags,
            details={'breaches': breaches} if breaches else {},
        )
