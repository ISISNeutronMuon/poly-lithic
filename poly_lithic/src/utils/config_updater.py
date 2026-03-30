"""Update an existing deployment config with variable info from a model file."""

from pathlib import Path

import yaml

from poly_lithic.src.utils.model_introspector import ModelIntrospector, ModelMetadata


class ConfigUpdater:
    """Patch a deployment_config.yaml using metadata introspected from a model.

    The updater modifies:
    - interface module variables (input + output PV names)
    - input_transformer symbols and variable mappings
    - model module config (model_path, model_factory_class, output variables)
    - output_transformer symbols and variable mappings
    """

    def __init__(self, config_path: str):
        self.config_path = Path(config_path).resolve()
        if not self.config_path.exists():
            raise FileNotFoundError(f'Config file not found: {self.config_path}')

    def update_from_model(
        self,
        model_file: str,
        factory_class: str = 'ModelFactory',
    ) -> Path:
        """Introspect *model_file* and patch the config in-place.

        Returns the path to the updated config file.
        """
        introspector = ModelIntrospector(model_file, factory_class)
        metadata = introspector.introspect()
        return self._apply_metadata(
            metadata, model_file=model_file, factory_class=factory_class
        )

    def update_from_metadata(self, metadata: ModelMetadata) -> Path:
        """Patch the config in-place using pre-built *metadata*.

        This is useful when the metadata comes from a JSON sample file
        rather than from a model file introspection.

        Returns the path to the updated config file.
        """
        return self._apply_metadata(metadata)

    def _apply_metadata(
        self,
        metadata: ModelMetadata,
        model_file: str | None = None,
        factory_class: str = 'ModelFactory',
    ) -> Path:
        with open(self.config_path) as fh:
            config = yaml.safe_load(fh)

        modules = config.get('modules', {})

        prefix = self._detect_prefix(modules)

        input_names = [v['name'] for v in metadata.input_variables]
        output_names = [v['name'] for v in metadata.output_variables]

        self._update_interface(modules, prefix, metadata)
        self._update_input_transformer(modules, prefix, input_names)
        self._update_model(
            modules,
            model_file or metadata.model_file,
            factory_class,
            metadata.output_variables,
        )
        self._update_output_transformer(modules, prefix, output_names)

        with open(self.config_path, 'w') as fh:
            yaml.dump(config, fh, default_flow_style=False, sort_keys=False)

        return self.config_path

    @staticmethod
    def _detect_prefix(modules: dict) -> str:
        """Try to infer the ``PROJECT:`` prefix from existing variable keys."""
        for key in ('p4p_server', 'fastapi_server', 'k2eg_interface'):
            mod = modules.get(key)
            if mod is None:
                continue
            variables = mod.get('config', {}).get('variables', {})
            for var_key in variables:
                # e.g. "MY_PROJECT:INPUT_A" → prefix "MY_PROJECT"
                if ':' in str(var_key):
                    return str(var_key).rsplit(':', 1)[0]
        return 'PROJECT'

    @staticmethod
    def _update_interface(modules: dict, prefix: str, metadata):
        """Replace interface variable entries with real model variables."""
        for key in ('p4p_server', 'fastapi_server', 'k2eg_interface'):
            mod = modules.get(key)
            if mod is None:
                continue
            cfg = mod.setdefault('config', {})
            is_fastapi = key == 'fastapi_server'
            new_vars = {}
            for var in metadata.input_variables:
                pv = f'{prefix}:{var["name"]}'
                if is_fastapi:
                    entry: dict = {
                        'mode': 'in',
                        'type': var.get('type', 'scalar'),
                        'default': var.get('default_value', 0.0),
                    }
                    if (
                        var.get('type', 'scalar') in ('waveform', 'array')
                        and 'length' in var
                    ):
                        entry['length'] = var['length']
                    elif var.get('type') == 'image' and 'image_size' in var:
                        entry['image_size'] = var['image_size']
                    new_vars[pv] = entry
                else:
                    entry = {'proto': 'pva', 'name': pv}
                    vtype = var.get('type', 'scalar')
                    if vtype != 'scalar':
                        entry['type'] = vtype
                    if 'default_value' in var:
                        entry['default'] = var['default_value']
                    if vtype in ('waveform', 'array') and 'length' in var:
                        entry['length'] = var['length']
                    elif vtype == 'image' and 'image_size' in var:
                        entry['image_size'] = var['image_size']
                    new_vars[pv] = entry
            for var in metadata.output_variables:
                pv = f'{prefix}:{var["name"]}'
                if is_fastapi:
                    entry = {
                        'mode': 'out',
                        'type': var.get('type', 'scalar'),
                        'default': var.get('default_value', 0.0),
                    }
                    if (
                        var.get('type', 'scalar') in ('waveform', 'array')
                        and 'length' in var
                    ):
                        entry['length'] = var['length']
                    elif var.get('type') == 'image' and 'image_size' in var:
                        entry['image_size'] = var['image_size']
                    new_vars[pv] = entry
                else:
                    entry = {'proto': 'pva', 'name': pv}
                    vtype = var.get('type', 'scalar')
                    if vtype != 'scalar':
                        entry['type'] = vtype
                    if 'default_value' in var:
                        entry['default'] = var['default_value']
                    if vtype in ('waveform', 'array') and 'length' in var:
                        entry['length'] = var['length']
                    elif vtype == 'image' and 'image_size' in var:
                        entry['image_size'] = var['image_size']
                    new_vars[pv] = entry
            cfg['variables'] = new_vars

    @staticmethod
    def _update_input_transformer(modules: dict, prefix: str, input_names: list[str]):
        """Update input_transformer symbols and variable mappings."""
        mod = modules.get('input_transformer')
        if mod is None:
            return
        cfg = mod.setdefault('config', {})
        cfg['symbols'] = [f'{prefix}:{n}' for n in input_names]
        cfg['variables'] = {n: {'formula': f'{prefix}:{n}'} for n in input_names}

    @staticmethod
    def _update_model(
        modules: dict,
        model_file: str,
        factory_class: str,
        output_variables: list[dict],
    ):
        """Update model config with correct path, factory class, and variables."""
        mod = modules.get('model')
        if mod is None:
            return
        cfg = mod.setdefault('config', {})
        # Update args if it's a LocalModelGetter
        if cfg.get('type') == 'LocalModelGetter':
            args = cfg.setdefault('args', {})
            args['model_path'] = (
                str(Path(model_file).name) if model_file else args.get('model_path', '')
            )
            args['model_factory_class'] = factory_class
        new_vars = {}
        for var in output_variables:
            entry: dict = {'type': var.get('type', 'scalar')}
            if var.get('type', 'scalar') in ('waveform', 'array') and 'length' in var:
                entry['length'] = var['length']
            elif var.get('type') == 'image' and 'image_size' in var:
                entry['image_size'] = var['image_size']
            new_vars[var['name']] = entry
        cfg['variables'] = new_vars

    @staticmethod
    def _update_output_transformer(modules: dict, prefix: str, output_names: list[str]):
        """Update output_transformer symbols and variable mappings."""
        mod = modules.get('output_transformer')
        if mod is None:
            return
        cfg = mod.setdefault('config', {})
        cfg['symbols'] = list(output_names)
        cfg['variables'] = {f'{prefix}:{n}': {'formula': n} for n in output_names}
