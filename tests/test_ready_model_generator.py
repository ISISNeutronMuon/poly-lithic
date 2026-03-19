"""Tests for model introspection, ready-model generation, and config updating."""

import json
import shutil
import pytest
import yaml
from pathlib import Path

from poly_lithic.src.utils.model_introspector import ModelIntrospector, ModelMetadata
from poly_lithic.src.utils.project_generator import ReadyModelProjectGenerator
from poly_lithic.src.utils.config_updater import ConfigUpdater

# Path to the existing lume-base test model
LUME_MODEL_FILE = str(Path(__file__).parent / 'model' / 'model_definition.py')


# ============================================================================
# ModelIntrospector tests
# ============================================================================


class TestModelIntrospector:
    """Tests for introspecting lume-compatible model files."""

    def test_introspect_inputs(self):
        introspector = ModelIntrospector(LUME_MODEL_FILE)
        metadata = introspector.introspect()
        input_names = [v['name'] for v in metadata.input_variables]
        assert input_names == ['x1', 'x2']

    def test_introspect_input_defaults(self):
        introspector = ModelIntrospector(LUME_MODEL_FILE)
        metadata = introspector.introspect()
        for var in metadata.input_variables:
            assert var['default_value'] == 0

    def test_introspect_input_ranges(self):
        introspector = ModelIntrospector(LUME_MODEL_FILE)
        metadata = introspector.introspect()
        for var in metadata.input_variables:
            assert var['value_range'] == [-100000, 1000000]

    def test_introspect_outputs(self):
        introspector = ModelIntrospector(LUME_MODEL_FILE)
        metadata = introspector.introspect()
        output_names = [v['name'] for v in metadata.output_variables]
        assert output_names == ['y']

    def test_introspect_factory_class(self):
        metadata = ModelIntrospector(LUME_MODEL_FILE).introspect()
        assert metadata.factory_class == 'ModelFactory'

    def test_introspect_model_file_path(self):
        metadata = ModelIntrospector(LUME_MODEL_FILE).introspect()
        assert metadata.model_file == str(Path(LUME_MODEL_FILE).resolve())

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ModelIntrospector('/nonexistent/model.py').introspect()

    def test_missing_factory_class(self):
        with pytest.raises(ValueError, match='Factory class'):
            ModelIntrospector(LUME_MODEL_FILE, 'NonExistentClass').introspect()

    def test_non_lume_model(self, tmp_path):
        """A model without input_variables should raise ValueError."""
        model_file = tmp_path / 'plain_model.py'
        model_file.write_text(
            'class PlainModel:\n'
            '    def evaluate(self, d): return d\n'
            'class ModelFactory:\n'
            '    def get_model(self): return PlainModel()\n'
        )
        with pytest.raises(ValueError, match='lume-compatible'):
            ModelIntrospector(str(model_file)).introspect()


# ============================================================================
# ReadyModelProjectGenerator tests
# ============================================================================


class TestReadyModelProjectGenerator:
    """Tests for generating projects from an existing model file."""

    @pytest.fixture
    def generator(self):
        return ReadyModelProjectGenerator()

    @pytest.fixture
    def output_dir(self, tmp_path):
        return tmp_path

    def test_generate_creates_project(self, generator, output_dir):
        path = generator.generate(
            name='lume-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
        )
        assert path.exists()
        assert (path / 'deployment_config.yaml').exists()
        assert (path / 'model_definition.py').exists()
        assert (path / 'env.json').exists()
        assert (path / 'README.md').exists()

    def test_model_file_is_copied(self, generator, output_dir):
        path = generator.generate(
            name='copy-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
        )
        original = Path(LUME_MODEL_FILE).read_text()
        assert (path / 'model_definition.py').read_text() == original

    def test_yaml_has_real_input_variables(self, generator, output_dir):
        path = generator.generate(
            name='vars-test',
            model_file=LUME_MODEL_FILE,
            interface_type='p4p_server',
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        iface_vars = data['modules']['p4p_server']['config']['variables']
        assert 'VARS_TEST:x1' in iface_vars
        assert 'VARS_TEST:x2' in iface_vars
        assert 'VARS_TEST:y' in iface_vars

    def test_yaml_input_transformer_uses_real_names(self, generator, output_dir):
        path = generator.generate(
            name='tx-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        tx = data['modules']['input_transformer']['config']
        assert 'TX_TEST:x1' in tx['symbols']
        assert 'TX_TEST:x2' in tx['symbols']
        assert 'x1' in tx['variables']
        assert 'x2' in tx['variables']

    def test_yaml_output_transformer_uses_real_names(self, generator, output_dir):
        path = generator.generate(
            name='out-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        tx = data['modules']['output_transformer']['config']
        assert 'y' in tx['symbols']
        assert 'OUT_TEST:y' in tx['variables']

    def test_yaml_model_variables(self, generator, output_dir):
        path = generator.generate(
            name='model-var-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        model_vars = data['modules']['model']['config']['variables']
        assert 'y' in model_vars

    def test_yaml_model_factory_class(self, generator, output_dir):
        path = generator.generate(
            name='factory-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
            factory_class='ModelFactory',
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        args = data['modules']['model']['config']['args']
        assert args['model_factory_class'] == 'ModelFactory'

    def test_fastapi_interface(self, generator, output_dir):
        path = generator.generate(
            name='fastapi-test',
            model_file=LUME_MODEL_FILE,
            interface_type='fastapi',
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        iface_vars = data['modules']['fastapi_server']['config']['variables']
        assert 'FASTAPI_TEST:x1' in iface_vars
        assert iface_vars['FASTAPI_TEST:x1']['mode'] == 'in'
        assert 'FASTAPI_TEST:y' in iface_vars
        assert iface_vars['FASTAPI_TEST:y']['mode'] == 'out'

    def test_k2eg_interface(self, generator, output_dir):
        path = generator.generate(
            name='k2eg-test',
            model_file=LUME_MODEL_FILE,
            interface_type='k2eg',
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        iface_vars = data['modules']['k2eg_interface']['config']['variables']
        assert 'K2EG_TEST:x1' in iface_vars
        assert 'K2EG_TEST:y' in iface_vars

    def test_duplicate_raises(self, generator, output_dir):
        generator.generate(
            name='dup-test',
            model_file=LUME_MODEL_FILE,
            output_dir=str(output_dir),
        )
        with pytest.raises(FileExistsError):
            generator.generate(
                name='dup-test',
                model_file=LUME_MODEL_FILE,
                output_dir=str(output_dir),
            )

    def test_docker_and_k8s_included(self, generator, output_dir):
        path = generator.generate(
            name='full-test',
            model_file=LUME_MODEL_FILE,
            include_docker=True,
            include_kubernetes=True,
            output_dir=str(output_dir),
        )
        assert (path / 'docker' / 'Dockerfile').exists()
        assert (path / 'k8s' / 'deployment.yaml').exists()


# ============================================================================
# ConfigUpdater tests
# ============================================================================


class TestConfigUpdater:
    """Test in-place config updating from a model file."""

    @pytest.fixture
    def generated_config(self, tmp_path):
        """Generate a project with placeholder names to update."""
        from poly_lithic.src.utils.project_generator import DeploymentProjectGenerator

        gen = DeploymentProjectGenerator()
        path = gen.generate(
            name='update-me',
            interface_type='p4p_server',
            model_source='local',
            output_dir=str(tmp_path),
        )
        return path / 'deployment_config.yaml'

    def test_update_replaces_interface_variables(self, generated_config):
        updater = ConfigUpdater(str(generated_config))
        updater.update_from_model(LUME_MODEL_FILE)

        with open(generated_config) as f:
            data = yaml.safe_load(f)

        iface_vars = data['modules']['p4p_server']['config']['variables']
        assert 'UPDATE_ME:x1' in iface_vars
        assert 'UPDATE_ME:x2' in iface_vars
        assert 'UPDATE_ME:y' in iface_vars
        # Placeholders should be gone
        assert 'UPDATE_ME:INPUT_A' not in iface_vars

    def test_update_replaces_input_transformer(self, generated_config):
        updater = ConfigUpdater(str(generated_config))
        updater.update_from_model(LUME_MODEL_FILE)

        with open(generated_config) as f:
            data = yaml.safe_load(f)

        tx = data['modules']['input_transformer']['config']
        assert 'UPDATE_ME:x1' in tx['symbols']
        assert 'UPDATE_ME:x2' in tx['symbols']
        assert 'x1' in tx['variables']
        assert 'x2' in tx['variables']

    def test_update_replaces_output_transformer(self, generated_config):
        updater = ConfigUpdater(str(generated_config))
        updater.update_from_model(LUME_MODEL_FILE)

        with open(generated_config) as f:
            data = yaml.safe_load(f)

        tx = data['modules']['output_transformer']['config']
        assert 'y' in tx['symbols']
        assert 'UPDATE_ME:y' in tx['variables']

    def test_update_replaces_model_variables(self, generated_config):
        updater = ConfigUpdater(str(generated_config))
        updater.update_from_model(LUME_MODEL_FILE)

        with open(generated_config) as f:
            data = yaml.safe_load(f)

        model_vars = data['modules']['model']['config']['variables']
        assert 'y' in model_vars
        assert 'max' not in model_vars

    def test_update_sets_model_path(self, generated_config):
        updater = ConfigUpdater(str(generated_config))
        updater.update_from_model(LUME_MODEL_FILE)

        with open(generated_config) as f:
            data = yaml.safe_load(f)

        args = data['modules']['model']['config']['args']
        assert args['model_path'] == 'model_definition.py'
        assert args['model_factory_class'] == 'ModelFactory'

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ConfigUpdater('/nonexistent/config.yaml')


# ============================================================================
# Lume-base end-to-end integration test
# ============================================================================


class TestLumeBaseIntegration:
    """End-to-end test: generate from lume model, load config, run model."""

    def test_generated_project_config_is_loadable(self, tmp_path):
        """Generate a project from the lume model and verify YAML is valid."""
        gen = ReadyModelProjectGenerator()
        path = gen.generate(
            name='lume-e2e',
            model_file=LUME_MODEL_FILE,
            interface_type='p4p_server',
            output_dir=str(tmp_path),
        )
        config_path = path / 'deployment_config.yaml'
        with open(config_path) as f:
            data = yaml.safe_load(f)

        assert data['deployment']['type'] == 'continuous'
        assert 'p4p_server' in data['modules']
        assert 'input_transformer' in data['modules']
        assert 'model' in data['modules']
        assert 'output_transformer' in data['modules']

    def test_model_evaluate_works(self):
        """Introspect and then call evaluate on the lume model."""
        introspector = ModelIntrospector(LUME_MODEL_FILE)
        metadata = introspector.introspect()

        # Load and evaluate with real inputs
        import importlib.util

        spec = importlib.util.spec_from_file_location('model_module', LUME_MODEL_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        model = module.ModelFactory().get_model()

        result = model.evaluate({'x1': 5.0, 'x2': 3.0})
        assert result['y'] == 5.0

    def test_update_then_validate(self, tmp_path):
        """Generate placeholder project, update from model, verify result."""
        from poly_lithic.src.utils.project_generator import DeploymentProjectGenerator

        gen = DeploymentProjectGenerator()
        path = gen.generate(
            name='update-e2e',
            interface_type='p4p_server',
            model_source='local',
            output_dir=str(tmp_path),
        )
        config_file = path / 'deployment_config.yaml'

        updater = ConfigUpdater(str(config_file))
        updater.update_from_model(LUME_MODEL_FILE)

        with open(config_file) as f:
            data = yaml.safe_load(f)

        # Verify variables were swapped
        iface_vars = data['modules']['p4p_server']['config']['variables']
        assert 'UPDATE_E2E:x1' in iface_vars
        assert 'UPDATE_E2E:x2' in iface_vars
        assert 'UPDATE_E2E:y' in iface_vars
        assert 'UPDATE_E2E:INPUT_A' not in iface_vars


# ============================================================================
# Dict variable extraction tests
# ============================================================================


class TestDictVariableExtraction:
    """Tests for extracting metadata from plain dict variables."""

    def test_extract_dict_scalar(self):
        var = {'name': 'x', 'type': 'scalar', 'default_value': 1.0}
        result = ModelIntrospector._extract_variable(var)
        assert result == {'name': 'x', 'type': 'scalar', 'default_value': 1.0}

    def test_extract_dict_defaults_to_scalar(self):
        var = {'name': 'x'}
        result = ModelIntrospector._extract_variable(var)
        assert result['type'] == 'scalar'

    def test_extract_dict_waveform(self):
        var = {'name': 'w', 'type': 'waveform', 'length': 100}
        result = ModelIntrospector._extract_variable(var)
        assert result['type'] == 'waveform'
        assert result['length'] == 100

    def test_extract_dict_image(self):
        var = {'name': 'img', 'type': 'image', 'image_size': {'x': 640, 'y': 480}}
        result = ModelIntrospector._extract_variable(var)
        assert result['type'] == 'image'
        assert result['image_size'] == {'x': 640, 'y': 480}

    def test_extract_dict_value_range(self):
        var = {'name': 'x', 'value_range': (0, 10)}
        result = ModelIntrospector._extract_variable(var)
        assert result['value_range'] == [0, 10]

    def test_extract_dict_preserves_all_keys(self):
        var = {
            'name': 'v',
            'type': 'waveform',
            'default_value': [1, 2, 3],
            'length': 3,
        }
        result = ModelIntrospector._extract_variable(var)
        assert result['default_value'] == [1, 2, 3]
        assert result['length'] == 3


# ============================================================================
# Module-level variables tests
# ============================================================================


class TestModuleLevelVariables:
    """Tests for introspecting module-level variable lists."""

    def test_module_level_dicts(self, tmp_path):
        model = tmp_path / 'model.py'
        model.write_text(
            'input_variables = [\n'
            "    {'name': 'a', 'type': 'scalar', 'default_value': 0.0},\n"
            "    {'name': 'b', 'type': 'waveform', 'length': 10},\n"
            ']\n'
            'output_variables = [\n'
            "    {'name': 'c', 'type': 'scalar'},\n"
            ']\n'
        )
        metadata = ModelIntrospector(str(model)).introspect()
        assert len(metadata.input_variables) == 2
        assert metadata.input_variables[0]['name'] == 'a'
        assert metadata.input_variables[1]['type'] == 'waveform'
        assert metadata.output_variables[0]['name'] == 'c'
        assert metadata.factory_class == ''

    def test_module_level_takes_precedence_over_factory(self, tmp_path):
        """Module-level variables should be used even if a factory exists."""
        model = tmp_path / 'model.py'
        model.write_text(
            "input_variables = [{'name': 'mod_in'}]\n"
            "output_variables = [{'name': 'mod_out'}]\n"
            '\n'
            'class ModelFactory:\n'
            '    def get_model(self):\n'
            "        raise RuntimeError('Should not be called')\n"
        )
        metadata = ModelIntrospector(str(model)).introspect()
        assert metadata.input_variables[0]['name'] == 'mod_in'
        assert metadata.output_variables[0]['name'] == 'mod_out'

    def test_non_list_module_vars_falls_through(self, tmp_path):
        """If module-level vars are not lists, fall back to factory."""
        model = tmp_path / 'model.py'
        model.write_text(
            "input_variables = 'not_a_list'\n"
            "output_variables = 'not_a_list'\n"
            '\n'
            'class _FakeModel:\n'
            "    input_variables = [type('V', (), {'name': 'a'})()]\n"
            "    output_variables = [type('V', (), {'name': 'b'})()]\n"
            '\n'
            'class ModelFactory:\n'
            '    def get_model(self): return _FakeModel()\n'
        )
        metadata = ModelIntrospector(str(model)).introspect()
        assert metadata.input_variables[0]['name'] == 'a'


# ============================================================================
# JSON sample file tests
# ============================================================================


class TestFromSampleFile:
    """Tests for ModelIntrospector.from_sample_file()."""

    def test_named_scalars(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(
            json.dumps({
                'input': {'x': 1.0, 'y': 2},
                'output': {'z': 3.5},
            })
        )
        metadata = ModelIntrospector.from_sample_file(str(sample))
        assert [v['name'] for v in metadata.input_variables] == ['x', 'y']
        assert metadata.input_variables[0]['type'] == 'scalar'
        assert metadata.output_variables[0]['default_value'] == 3.5

    def test_unnamed_variables(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(
            json.dumps({
                'input': [1.0, 2.0, 3.0],
                'output': [10.0],
            })
        )
        metadata = ModelIntrospector.from_sample_file(str(sample))
        assert metadata.input_variables[0]['name'] == 'input_0'
        assert metadata.input_variables[2]['name'] == 'input_2'
        assert metadata.output_variables[0]['name'] == 'output_0'

    def test_waveform_inference(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(
            json.dumps({
                'input': {'wave': [1.0, 2.0, 3.0]},
                'output': {'result': 0.0},
            })
        )
        metadata = ModelIntrospector.from_sample_file(str(sample))
        wave_var = metadata.input_variables[0]
        assert wave_var['type'] == 'waveform'
        assert wave_var['length'] == 3
        assert wave_var['default_value'] == [1.0, 2.0, 3.0]

    def test_image_inference(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(
            json.dumps({
                'input': {'img': [[1, 2], [3, 4], [5, 6]]},
                'output': {'val': 0.0},
            })
        )
        metadata = ModelIntrospector.from_sample_file(str(sample))
        img_var = metadata.input_variables[0]
        assert img_var['type'] == 'image'
        assert img_var['image_size'] == {'x': 2, 'y': 3}

    def test_empty_list_defaults_to_scalar(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(
            json.dumps({
                'input': {'empty': []},
                'output': {'val': 0.0},
            })
        )
        metadata = ModelIntrospector.from_sample_file(str(sample))
        assert metadata.input_variables[0]['type'] == 'scalar'

    def test_missing_keys_raises(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(json.dumps({'input': {'x': 1.0}}))
        with pytest.raises(ValueError, match='input.*output'):
            ModelIntrospector.from_sample_file(str(sample))

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ModelIntrospector.from_sample_file('/nonexistent/sample.json')

    def test_invalid_group_type(self, tmp_path):
        sample = tmp_path / 'sample.json'
        sample.write_text(json.dumps({'input': 'bad', 'output': {'x': 1}}))
        with pytest.raises(ValueError, match='dict.*list'):
            ModelIntrospector.from_sample_file(str(sample))


# ============================================================================
# Type-aware template generation tests
# ============================================================================


class TestTypeAwareGeneration:
    """Tests that generated configs propagate variable types correctly."""

    @pytest.fixture
    def generator(self):
        return ReadyModelProjectGenerator()

    def test_fastapi_waveform_type(self, generator, tmp_path):
        metadata = ModelMetadata(
            input_variables=[
                {
                    'name': 'wave_in',
                    'type': 'waveform',
                    'length': 50,
                    'default_value': 0.0,
                },
            ],
            output_variables=[
                {'name': 'wave_out', 'type': 'waveform', 'length': 100},
            ],
        )
        path = generator.generate(
            name='wave-test',
            interface_type='fastapi',
            output_dir=str(tmp_path),
            metadata=metadata,
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        iface_vars = data['modules']['fastapi_server']['config']['variables']
        assert iface_vars['WAVE_TEST:wave_in']['type'] == 'waveform'
        assert iface_vars['WAVE_TEST:wave_out']['type'] == 'waveform'

    def test_fastapi_image_type(self, generator, tmp_path):
        metadata = ModelMetadata(
            input_variables=[{'name': 'x', 'type': 'scalar'}],
            output_variables=[
                {'name': 'img', 'type': 'image', 'image_size': {'x': 64, 'y': 48}},
            ],
        )
        path = generator.generate(
            name='img-test',
            interface_type='fastapi',
            output_dir=str(tmp_path),
            metadata=metadata,
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)

        model_vars = data['modules']['model']['config']['variables']
        assert model_vars['img']['type'] == 'image'

    def test_model_stub_rendered_when_no_model_file(self, generator, tmp_path):
        metadata = ModelMetadata(
            input_variables=[{'name': 'a', 'type': 'scalar'}],
            output_variables=[{'name': 'b', 'type': 'scalar'}],
        )
        path = generator.generate(
            name='stub-test',
            output_dir=str(tmp_path),
            metadata=metadata,
        )
        assert (path / 'model_definition.py').exists()


# ============================================================================
# Type-aware ConfigUpdater tests
# ============================================================================


class TestTypeAwareConfigUpdater:
    """Test that ConfigUpdater propagates variable types."""

    @pytest.fixture
    def fastapi_config(self, tmp_path):
        from poly_lithic.src.utils.project_generator import DeploymentProjectGenerator

        gen = DeploymentProjectGenerator()
        path = gen.generate(
            name='type-upd',
            interface_type='fastapi',
            model_source='local',
            output_dir=str(tmp_path),
        )
        return path / 'deployment_config.yaml'

    def test_update_from_metadata_waveform(self, fastapi_config):
        metadata = ModelMetadata(
            input_variables=[
                {
                    'name': 'sig',
                    'type': 'waveform',
                    'length': 256,
                    'default_value': 0.0,
                },
            ],
            output_variables=[
                {'name': 'result', 'type': 'scalar'},
            ],
        )
        updater = ConfigUpdater(str(fastapi_config))
        updater.update_from_metadata(metadata)

        with open(fastapi_config) as f:
            data = yaml.safe_load(f)

        iface_vars = data['modules']['fastapi_server']['config']['variables']
        assert iface_vars['TYPE_UPD:sig']['type'] == 'waveform'
        assert iface_vars['TYPE_UPD:sig']['length'] == 256

    def test_update_from_metadata_image(self, fastapi_config):
        metadata = ModelMetadata(
            input_variables=[{'name': 'x', 'type': 'scalar'}],
            output_variables=[
                {'name': 'img', 'type': 'image', 'image_size': {'x': 32, 'y': 32}},
            ],
        )
        updater = ConfigUpdater(str(fastapi_config))
        updater.update_from_metadata(metadata)

        with open(fastapi_config) as f:
            data = yaml.safe_load(f)

        model_vars = data['modules']['model']['config']['variables']
        assert model_vars['img']['type'] == 'image'
        assert model_vars['img']['image_size'] == {'x': 32, 'y': 32}

    def test_update_from_metadata_no_model_file(self, fastapi_config):
        """update_from_metadata works even without a model_file in metadata."""
        metadata = ModelMetadata(
            input_variables=[{'name': 'a', 'type': 'scalar'}],
            output_variables=[{'name': 'b', 'type': 'scalar'}],
        )
        updater = ConfigUpdater(str(fastapi_config))
        result = updater.update_from_metadata(metadata)
        assert result.exists()


# ============================================================================
# Lume-base type extraction tests
# ============================================================================


class TestLumeTypeExtraction:
    """Test that lume-base variable types are inferred from class names."""

    def test_lume_scalar_type(self):
        metadata = ModelIntrospector(LUME_MODEL_FILE).introspect()
        # The test model uses ScalarInputVariable / ScalarOutputVariable
        for var in metadata.input_variables:
            assert var['type'] == 'scalar'
