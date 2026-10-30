"""
Evaluators module.

Contains base evaluator classes and built-in evaluator implementations
for online model evaluation against real system data.
"""

from poly_lithic.src.evaluators.BaseEvaluator import BaseEvaluator, EvalResult
from poly_lithic.src.evaluators.rolling_stats import RollingStatsEvaluator
from poly_lithic.src.evaluators.drift_detection import DriftDetectionEvaluator
from poly_lithic.src.evaluators.threshold_evaluator import ThresholdEvaluator
from poly_lithic.src.evaluators.alignment_buffer import AlignmentBuffer, PairedSample

registered_evaluators = {
    'RollingStatsEvaluator': RollingStatsEvaluator,
    'DriftDetectionEvaluator': DriftDetectionEvaluator,
    'ThresholdEvaluator': ThresholdEvaluator,
}

__all__ = [
    'BaseEvaluator',
    'EvalResult',
    'RollingStatsEvaluator',
    'DriftDetectionEvaluator',
    'ThresholdEvaluator',
    'AlignmentBuffer',
    'PairedSample',
    'registered_evaluators',
]
