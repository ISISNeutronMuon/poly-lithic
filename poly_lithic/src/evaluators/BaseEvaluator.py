from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    """Result from an evaluator run.

    Attributes:
        metrics: dict of metric_name -> value (e.g. {"rmse": 0.12, "mae": 0.08})
        flags: dict of flag_name -> bool (e.g. {"drift_detected": True})
        details: optional dict with extra diagnostic info
    """

    metrics: dict[str, float] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


class BaseEvaluator(ABC):
    """Abstract base class for online model evaluators."""

    @abstractmethod
    def __init__(self, config: dict):
        """Initialise from YAML config dict."""
        pass

    @abstractmethod
    def evaluate(
        self,
        predictions: dict[str, list[float]],
        actuals: dict[str, list[float]],
        timestamps: list[float] | None = None,
    ) -> EvalResult:
        """Run evaluation on paired prediction/actual windows.

        Args:
            predictions: {pv_name: [values...]} prediction window per mapped PV.
            actuals: {pv_name: [values...]} ground truth window per mapped PV.
            timestamps: optional list of timestamps for the pairs.

        Returns:
            EvalResult with computed metrics and flags.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this evaluator type."""
        pass
