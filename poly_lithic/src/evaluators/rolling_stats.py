"""Rolling statistics evaluator — RMSE, MAE, mean bias, R²."""

import math
from poly_lithic.src.evaluators.BaseEvaluator import BaseEvaluator, EvalResult


class RollingStatsEvaluator(BaseEvaluator):
    """Computes rolling error statistics over a window of paired samples."""

    def __init__(self, config: dict):
        self.config = config
        self._enabled_metrics = config.get('metrics', ['rmse', 'mae', 'mean_bias', 'r_squared'])

    @property
    def name(self) -> str:
        return 'RollingStatsEvaluator'

    def evaluate(
        self,
        predictions: dict[str, list[float]],
        actuals: dict[str, list[float]],
        timestamps: list[float] | None = None,
    ) -> EvalResult:
        metrics: dict[str, float] = {}
        all_preds: list[float] = []
        all_actuals: list[float] = []

        for pv in predictions:
            preds = predictions[pv]
            acts = actuals.get(pv, [])
            n = min(len(preds), len(acts))
            if n == 0:
                continue
            all_preds.extend(preds[:n])
            all_actuals.extend(acts[:n])

        n = len(all_preds)
        if n == 0:
            return EvalResult(metrics={m: float('nan') for m in self._enabled_metrics})

        errors = [p - a for p, a in zip(all_preds, all_actuals)]
        abs_errors = [abs(e) for e in errors]
        sq_errors = [e * e for e in errors]

        if 'rmse' in self._enabled_metrics:
            metrics['rmse'] = math.sqrt(sum(sq_errors) / n)

        if 'mae' in self._enabled_metrics:
            metrics['mae'] = sum(abs_errors) / n

        if 'mean_bias' in self._enabled_metrics:
            metrics['mean_bias'] = sum(errors) / n

        if 'r_squared' in self._enabled_metrics:
            mean_actual = sum(all_actuals) / n
            ss_res = sum(sq_errors)
            ss_tot = sum((a - mean_actual) ** 2 for a in all_actuals)
            metrics['r_squared'] = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else float('nan')

        return EvalResult(metrics=metrics)
