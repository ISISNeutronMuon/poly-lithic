"""Workflow handlers — actions triggered when evaluation conditions are met.

Supports:
- BrokerMessageHandler: publishes a Message to a configured broker topic
- WebhookHandler: HTTP POST to a URL with evaluation results as JSON
- ScriptHandler: executes a shell command or Python callable
"""

import ast
import json
import logging
import math
import operator
import re
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BaseWorkflowHandler(ABC):
    """Abstract base for workflow actions triggered by evaluation results."""

    @abstractmethod
    def __init__(self, config: dict):
        pass

    @abstractmethod
    def handle(self, eval_result: Any, context: dict) -> None:
        """Execute the workflow action.

        Args:
            eval_result: EvalResult dataclass from the evaluator.
            context: dict with keys like 'broker', 'topic', etc.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


_PLACEHOLDER_FMT = '__pl_var_{}__'
_NAME_BOUNDARY_CHARS = r'\w:/.'

_CMP_OPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


class UnknownVariableError(NameError):
    """Raised when a condition references a name not in metrics/flags."""


def _substitute_names(condition: str, names: list[str]) -> tuple[str, dict[str, str]]:
    """Replace metric/flag names in *condition* with identifier-safe placeholders.

    Names are replaced longest-first and only at name boundaries, so a name
    that is a substring of another (``rmse`` vs ``rmse_ratio``) cannot
    corrupt it.  Returns the rewritten expression and a placeholder -> name map.
    """
    mapping: dict[str, str] = {}
    expr_str = condition
    for i, name in enumerate(sorted(names, key=len, reverse=True)):
        placeholder = _PLACEHOLDER_FMT.format(i)
        pattern = (
            rf'(?<![{_NAME_BOUNDARY_CHARS}]){re.escape(name)}'
            rf'(?![{_NAME_BOUNDARY_CHARS}])'
        )
        expr_str, n = re.subn(pattern, placeholder, expr_str)
        if n:
            mapping[placeholder] = name
    return expr_str, mapping


def _eval_node(node: ast.AST, values: dict[str, Any]) -> Any:
    """Evaluate a whitelisted AST node; anything else raises ValueError."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, values)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (bool, int, float)):
            return node.value
        raise ValueError(f'Unsupported constant: {node.value!r}')
    if isinstance(node, ast.Name):
        if node.id in values:
            return values[node.id]
        if node.id in ('True', 'False'):
            return node.id == 'True'
        raise UnknownVariableError(f'Unknown variable: {node.id}')
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(bool(_eval_node(v, values)) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(bool(_eval_node(v, values)) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, values)
        if isinstance(node.op, (ast.Not, ast.Invert)):
            return not bool(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
    if isinstance(node, ast.BinOp):
        # & and | are treated as logical and/or (kept for SymPy-style conditions)
        if isinstance(node.op, ast.BitAnd):
            return bool(_eval_node(node.left, values)) and bool(
                _eval_node(node.right, values)
            )
        if isinstance(node.op, ast.BitOr):
            return bool(_eval_node(node.left, values)) or bool(
                _eval_node(node.right, values)
            )
        op = _BIN_OPS.get(type(node.op))
        if op is not None:
            return op(_eval_node(node.left, values), _eval_node(node.right, values))
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, values)
        for op_node, comparator in zip(node.ops, node.comparators):
            op = _CMP_OPS.get(type(op_node))
            if op is None:
                raise ValueError(f'Unsupported comparison: {type(op_node).__name__}')
            right = _eval_node(comparator, values)
            if not op(left, right):
                return False
            left = right
        return True
    raise ValueError(f'Unsupported expression element: {type(node).__name__}')


def check_condition(condition: str, eval_result: Any) -> bool:
    """Evaluate a condition string against eval_result metrics and flags.

    The condition is parsed with :mod:`ast` and evaluated over a small
    whitelisted subset of Python expression syntax (no ``eval``):

    - names: any key of ``eval_result.metrics`` or ``eval_result.flags``,
      written verbatim — including per-PV names containing ``:``, ``/`` or
      ``.`` such as ``ML:PRED:TEMP/max_abs_error``.  Flags evaluate to
      ``True``/``False``; if a key exists in both, the metric wins.
    - literals: int / float numbers, ``True``, ``False``
    - comparisons: ``>``, ``>=``, ``<``, ``<=``, ``==``, ``!=`` (chainable,
      e.g. ``0.1 < rmse < 0.5``)
    - arithmetic: ``+ - * / // % **`` and unary ``-``/``+``
    - logic: ``and``, ``or``, ``not`` with normal Python precedence
      (comparisons bind tighter than ``and``/``or``); ``&``, ``|`` and ``~``
      are accepted as logical and/or/not, but bind tighter than comparisons,
      so parenthesise: ``(mae > 0.1) & drift_detected``.
    - parentheses for grouping

    An empty condition returns ``True``.  Unknown variables, unsupported
    syntax or evaluation errors log a warning and return ``False``.

    Examples:
        "rmse > 0.5"
        "drift_detected"
        "mae > 0.1 and drift_detected"
        "not drift_detected or rmse < 0.2"
        "ML:PRED:TEMP/max_abs_error > 1 and ML:PRED:TEMP/abs_threshold_exceeded"
    """
    if not condition or not condition.strip():
        return True

    by_name: dict[str, Any] = {k: bool(v) for k, v in eval_result.flags.items()}
    by_name.update(eval_result.metrics)

    expr_str, mapping = _substitute_names(condition.strip(), list(by_name))
    values = {placeholder: by_name[name] for placeholder, name in mapping.items()}

    try:
        tree = ast.parse(expr_str, mode='eval')
        unknown = sorted({
            n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id not in values
            and n.id not in ('True', 'False')
        })
        if unknown:
            raise UnknownVariableError(', '.join(unknown))
        return bool(_eval_node(tree, values))
    except UnknownVariableError as e:
        logger.warning(f'Condition "{condition}" references an unknown variable: {e}')
        return False
    except Exception as e:
        logger.warning(f'Failed to evaluate condition "{condition}": {e}')
        return False


def _json_safe(value: Any) -> Any:
    """Recursively replace non-finite floats (inf / nan) with ``None``."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if callable(getattr(value, 'tolist', None)):
        # numpy scalars / arrays -> native Python types
        return _json_safe(value.tolist())
    return value


def build_json_payload(eval_result: Any) -> str:
    """Serialise an EvalResult to strict JSON (non-finite floats become null)."""
    return json.dumps(
        _json_safe({
            'metrics': eval_result.metrics,
            'flags': eval_result.flags,
            'details': eval_result.details,
        }),
        allow_nan=False,
    )


class BrokerMessageHandler(BaseWorkflowHandler):
    """Publishes an evaluation Message into the broker queue."""

    def __init__(self, config: dict):
        self._topic = config.get('topic', 'eval_alarm')

    @property
    def name(self) -> str:
        return 'BrokerMessageHandler'

    def handle(self, eval_result: Any, context: dict) -> None:
        """Pushes a message dict into context['messages'] for the observer to publish."""
        messages = context.setdefault('messages', [])
        # Build a value dict from metrics + flags
        value_dict = {}
        for k, v in eval_result.metrics.items():
            value_dict[k] = {'value': v}
        for k, v in eval_result.flags.items():
            value_dict[k] = {'value': int(v)}
        messages.append({'topic': self._topic, 'value': value_dict})


class WebhookHandler(BaseWorkflowHandler):
    """Sends evaluation results via HTTP POST to a configured URL."""

    def __init__(self, config: dict):
        self._url = config['url']
        self._timeout = config.get('timeout', 10)
        self._headers = config.get('headers', {'Content-Type': 'application/json'})

    @property
    def name(self) -> str:
        return 'WebhookHandler'

    def handle(self, eval_result: Any, context: dict) -> None:
        import urllib.request

        payload = build_json_payload(eval_result).encode('utf-8')

        req = urllib.request.Request(
            self._url,
            data=payload,
            headers=self._headers,
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                logger.info(f'Webhook {self._url} responded {resp.status}')
        except Exception as e:
            logger.error(f'Webhook {self._url} failed: {e}')


class ScriptHandler(BaseWorkflowHandler):
    """Executes a shell command, passing evaluation results as JSON via stdin."""

    def __init__(self, config: dict):
        self._command = config['command']
        self._timeout = config.get('timeout', 30)

    @property
    def name(self) -> str:
        return 'ScriptHandler'

    def handle(self, eval_result: Any, context: dict) -> None:
        payload = build_json_payload(eval_result)
        try:
            result = subprocess.run(
                self._command,
                input=payload,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            if result.returncode != 0:
                logger.warning(
                    f'Script "{self._command}" exited {result.returncode}: {result.stderr}'
                )
            else:
                logger.info(f'Script "{self._command}" completed successfully')
        except subprocess.TimeoutExpired:
            logger.error(f'Script "{self._command}" timed out after {self._timeout}s')
        except Exception as e:
            logger.error(f'Script "{self._command}" failed: {e}')


class PVAlarmHandler(BaseWorkflowHandler):
    """Writes a PV value plus alarm severity and status message.

    When the condition fires, the handler emits a broker message whose
    value dict contains a single PV with ``value`` (default 1) and an
    ``alarm`` struct (severity + message).  When the condition is *not*
    met the observer will not call this handler, so add a complementary
    workflow entry with an inverted condition, ``value: 0`` and
    ``severity: 0`` to clear the alarm.

    Config keys::

        type: pv_alarm
        condition: "drift_detected"
        pv: "ML:LOCAL:EVAL_ALARM"
        topic: "eval_alarm_write"        # broker topic for the interface sub
        severity: 2                      # 0=NO_ALARM, 1=MINOR, 2=MAJOR
        message: "Drift detected"        # alarm status string
        value: 1                         # PV value to write (use 0 to clear)
    """

    def __init__(self, config: dict):
        self._pv = config['pv']
        self._topic = config.get('topic', 'eval_alarm_write')
        self._severity = int(config.get('severity', 2))
        self._message = config.get('message', 'Evaluation alarm')
        self._value = config.get('value', 1)

    @property
    def name(self) -> str:
        return 'PVAlarmHandler'

    def handle(self, eval_result: Any, context: dict) -> None:
        messages = context.setdefault('messages', [])
        messages.append({
            'topic': self._topic,
            'value': {
                self._pv: {
                    'value': self._value,
                    'alarm': {
                        'severity': self._severity,
                        'status': 0,
                        'message': self._message,
                    },
                },
            },
        })


HANDLER_REGISTRY: dict[str, type[BaseWorkflowHandler]] = {
    'broker_message': BrokerMessageHandler,
    'webhook': WebhookHandler,
    'script': ScriptHandler,
    'pv_alarm': PVAlarmHandler,
}


def build_handlers(workflow_configs: list[dict]) -> list[tuple[str, BaseWorkflowHandler]]:
    """Build workflow handlers from a list of config dicts.

    Returns:
        List of (condition_string, handler) tuples.
    """
    handlers = []
    for wf_cfg in workflow_configs:
        handler_type = wf_cfg.get('type', 'broker_message')
        condition = wf_cfg.get('condition', '')
        if handler_type not in HANDLER_REGISTRY:
            logger.warning(f'Unknown workflow handler type: {handler_type}')
            continue
        handler = HANDLER_REGISTRY[handler_type](wf_cfg)
        handlers.append((condition, handler))
    return handlers
