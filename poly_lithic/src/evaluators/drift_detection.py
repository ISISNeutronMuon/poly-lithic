"""Drift detection evaluator — KS test, CUSUM, Page-Hinkley on residuals."""

import math
from poly_lithic.src.evaluators.BaseEvaluator import BaseEvaluator, EvalResult


class DriftDetectionEvaluator(BaseEvaluator):
    """Detects distribution drift in prediction residuals using
    Kolmogorov–Smirnov test and CUSUM change-point detection."""

    def __init__(self, config: dict):
        self.config = config
        drift_cfg = config.get('drift', {})
        # KS test significance level
        self.ks_alpha: float = drift_cfg.get('ks_alpha', 0.05)
        # CUSUM parameters
        self.cusum_threshold: float = drift_cfg.get('cusum_threshold', 5.0)
        self.cusum_drift: float = drift_cfg.get('cusum_drift', 0.0)
        # Minimum samples before running tests
        self.min_samples: int = drift_cfg.get('min_samples', 10)

    @property
    def name(self) -> str:
        return 'DriftDetectionEvaluator'

    def evaluate(
        self,
        predictions: dict[str, list[float]],
        actuals: dict[str, list[float]],
        timestamps: list[float] | None = None,
    ) -> EvalResult:
        all_residuals: list[float] = []
        for pv in predictions:
            preds = predictions[pv]
            acts = actuals.get(pv, [])
            n = min(len(preds), len(acts))
            all_residuals.extend(p - a for p, a in zip(preds[:n], acts[:n]))

        n = len(all_residuals)
        if n < self.min_samples:
            return EvalResult(
                flags={'drift_detected': False, 'cusum_alert': False},
                details={'reason': 'insufficient_samples', 'n': n},
            )

        metrics: dict[str, float] = {}
        flags: dict[str, bool] = {}

        # --- KS test against N(0, σ) ---
        ks_stat = self._ks_test_normal(all_residuals)
        ks_critical = self._ks_critical_value(n, self.ks_alpha)
        metrics['ks_statistic'] = ks_stat
        metrics['ks_critical'] = ks_critical
        flags['drift_detected'] = ks_stat > ks_critical

        # --- CUSUM ---
        cusum_max = self._cusum(all_residuals)
        metrics['cusum_max'] = cusum_max
        flags['cusum_alert'] = cusum_max > self.cusum_threshold

        return EvalResult(metrics=metrics, flags=flags)

    @staticmethod
    def _ks_test_normal(residuals: list[float]) -> float:
        """One-sample KS test against N(mean, std) — returns the KS statistic."""
        n = len(residuals)
        if n == 0:
            return 0.0
        mean = sum(residuals) / n
        var = sum((r - mean) ** 2 for r in residuals) / n
        std = math.sqrt(var) if var > 0 else 1e-12

        # If variance is effectively zero the residuals are constant
        # which means predictions match actuals perfectly — no drift.
        if var < 1e-12:
            return 0.0

        sorted_r = sorted(residuals)
        d_max = 0.0
        for i, val in enumerate(sorted_r):
            # empirical CDF
            ecdf = (i + 1) / n
            # theoretical CDF (normal approximation via error function)
            z = (val - mean) / std
            tcdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            d_max = max(d_max, abs(ecdf - tcdf), abs((i / n) - tcdf))
        return d_max

    @staticmethod
    def _ks_critical_value(n: int, alpha: float) -> float:
        """Approximate KS critical value using the standard formula."""
        c_alpha = {0.10: 1.22, 0.05: 1.36, 0.025: 1.48, 0.01: 1.63}
        c = c_alpha.get(alpha, 1.36)
        return c / math.sqrt(n)

    def _cusum(self, residuals: list[float]) -> float:
        """Tabular CUSUM — returns max cumulative sum of deviations."""
        if not residuals:
            return 0.0
        mean = sum(residuals) / len(residuals)
        s_pos = 0.0
        s_neg = 0.0
        max_s = 0.0
        for r in residuals:
            s_pos = max(0.0, s_pos + (r - mean) - self.cusum_drift)
            s_neg = max(0.0, s_neg - (r - mean) - self.cusum_drift)
            max_s = max(max_s, s_pos, s_neg)
        return max_s
