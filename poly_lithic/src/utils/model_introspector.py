"""Introspect a model definition file to extract variable metadata.

Uses the same ``importlib.util`` loading pattern as
:class:`~poly_lithic.src.model_utils.LocalModelGetter.LocalModelGetter`.

Supports three input modes:

1. **lume-base model file** — a ``.py`` file with a factory class (default
   ``ModelFactory``) whose ``get_model()`` returns a model with
   ``input_variables`` / ``output_variables`` (lume-base objects *or* plain
   dicts).
2. **Module-level variables** — a ``.py`` file that defines
   ``input_variables`` and ``output_variables`` as module-level lists of
   dicts (no factory class required).
3. **JSON sample file** — a ``.json`` file with ``"input"`` and ``"output"``
   keys holding sample data from which variable names and types are inferred.
"""

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

# Mapping from lume-base class names to poly-lithic variable types.
_LUME_CLASS_TYPE_MAP: dict[str, str] = {
    'ScalarVariable': 'scalar',
    'ArrayVariable': 'waveform',
    'ImageVariable': 'image',
}


@dataclass
class ModelMetadata:
    """Metadata extracted from a lume-compatible model."""

    input_variables: list[dict] = field(default_factory=list)
    output_variables: list[dict] = field(default_factory=list)
    factory_class: str = 'ModelFactory'
    model_file: str = ''


class ModelIntrospector:
    """Load a model definition file and extract input/output variable info.

    The model can follow the lume-base convention (factory class producing a
    model with ``input_variables`` / ``output_variables``) **or** simply
    define those lists at module level as plain dicts.
    """

    def __init__(self, model_file: str, factory_class: str = 'ModelFactory'):
        self.model_file = Path(model_file).resolve()
        self.factory_class = factory_class

    def introspect(self) -> ModelMetadata:
        """Load the model and return :class:`ModelMetadata`.

        Resolution order:

        1. Module-level ``input_variables`` / ``output_variables`` (plain
           dicts — no factory needed).
        2. Factory class ``get_model()`` → model attributes (lume-base
           objects or dicts).
        """
        if not self.model_file.exists():
            raise FileNotFoundError(f'Model file not found: {self.model_file}')

        spec = importlib.util.spec_from_file_location(
            'model_module', str(self.model_file)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # --- Try module-level variables first ---
        mod_inputs = getattr(module, 'input_variables', None)
        mod_outputs = getattr(module, 'output_variables', None)
        if isinstance(mod_inputs, list) and isinstance(mod_outputs, list):
            input_vars = [self._extract_variable(v) for v in mod_inputs]
            output_vars = [self._extract_variable(v) for v in mod_outputs]
            return ModelMetadata(
                input_variables=input_vars,
                output_variables=output_vars,
                factory_class='',
                model_file=str(self.model_file),
            )

        # --- Fall back to factory class ---
        factory_cls = getattr(module, self.factory_class, None)
        if factory_cls is None:
            raise ValueError(
                f"Factory class '{self.factory_class}' not found in {self.model_file}"
            )

        model = factory_cls().get_model()

        if not hasattr(model, 'input_variables') or not hasattr(
            model, 'output_variables'
        ):
            raise ValueError(
                f"Model from '{self.factory_class}' does not expose "
                "'input_variables' and 'output_variables'. "
                'Only lume-compatible models are supported for auto-generation.'
            )

        input_vars = [self._extract_variable(v) for v in model.input_variables]
        output_vars = [self._extract_variable(v) for v in model.output_variables]

        return ModelMetadata(
            input_variables=input_vars,
            output_variables=output_vars,
            factory_class=self.factory_class,
            model_file=str(self.model_file),
        )

    # ------------------------------------------------------------------
    # JSON sample file
    # ------------------------------------------------------------------

    @classmethod
    def from_sample_file(cls, sample_path: str) -> ModelMetadata:
        """Build :class:`ModelMetadata` by inferring types from a JSON sample.

        The JSON file must contain ``"input"`` and ``"output"`` keys.  Each
        value can be either:

        * A **dict** (named) — keys become variable names, values are samples.
        * A **list** (unnamed) — names are auto-generated as ``input_0``,
          ``input_1``, … / ``output_0``, ``output_1``, …

        Type inference per value:

        * ``int`` / ``float`` → ``scalar``
        * 1-D list of numbers → ``waveform``
        * 2-D list of lists → ``image``
        """
        path = Path(sample_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f'Sample file not found: {path}')

        with open(path) as fh:
            data = json.load(fh)

        if 'input' not in data or 'output' not in data:
            raise ValueError("Sample JSON must contain 'input' and 'output' keys")

        input_vars = cls._parse_sample_group(data['input'], 'input')
        output_vars = cls._parse_sample_group(data['output'], 'output')

        return ModelMetadata(
            input_variables=input_vars,
            output_variables=output_vars,
            factory_class='',
            model_file='',
        )

    @classmethod
    def _parse_sample_group(cls, group, prefix: str) -> list[dict]:
        """Parse the ``"input"`` or ``"output"`` section of a sample file."""
        if isinstance(group, dict):
            return [cls._infer_variable(name, value) for name, value in group.items()]
        if isinstance(group, list):
            return [
                cls._infer_variable(f'{prefix}_{i}', value)
                for i, value in enumerate(group)
            ]
        raise ValueError(
            f"'{prefix}' must be a dict (named) or list (unnamed), "
            f'got {type(group).__name__}'
        )

    @staticmethod
    def _infer_variable(name: str, value) -> dict:
        """Infer variable metadata from a single sample value."""
        info: dict = {'name': name}

        if isinstance(value, (int, float)):
            info['type'] = 'scalar'
            info['default_value'] = value
        elif isinstance(value, list):
            if not value:
                info['type'] = 'scalar'
                info['default_value'] = 0.0
            elif isinstance(value[0], list):
                # 2-D → image
                info['type'] = 'image'
                rows = len(value)
                cols = len(value[0]) if value else 0
                info['image_size'] = {'x': cols, 'y': rows}
            else:
                # 1-D → waveform
                info['type'] = 'waveform'
                info['length'] = len(value)
                info['default_value'] = value
        else:
            info['type'] = 'scalar'
            info['default_value'] = 0.0

        return info

    # ------------------------------------------------------------------
    # Variable extraction (objects or dicts)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_variable(var) -> dict:
        """Pull metadata from a lume-base variable object **or** a plain dict.

        When *var* is a dict the keys are used directly.  When it is an
        object (e.g. ``ScalarVariable``) attributes are read via ``getattr``.
        """
        if isinstance(var, dict):
            info: dict = {'name': var['name']}
            for key in ('type', 'default_value', 'value_range', 'length', 'image_size'):
                if key in var:
                    val = var[key]
                    if key == 'value_range':
                        val = list(val)
                    info[key] = val
            # Default type to scalar when not specified
            info.setdefault('type', 'scalar')
            return info

        # Object path (lume-base variables)
        info = {'name': var.name}
        if hasattr(var, 'default_value') and var.default_value is not None:
            info['default_value'] = var.default_value
        if hasattr(var, 'value_range') and var.value_range is not None:
            info['value_range'] = list(var.value_range)

        # Infer type from class name
        cls_name = type(var).__name__
        info['type'] = _LUME_CLASS_TYPE_MAP.get(cls_name, 'scalar')

        return info
