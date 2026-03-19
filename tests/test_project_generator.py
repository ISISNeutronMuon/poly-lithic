"""Tests for the deployment project generator."""

import pytest
import yaml
from pathlib import Path

from poly_lithic.src.utils.project_generator import (
    BaseProjectGenerator,
    DeploymentProjectGenerator,
)


@pytest.fixture
def generator():
    return DeploymentProjectGenerator()


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path


class TestBaseProjectGenerator:
    """Test the abstract base class helpers."""

    def test_normalize_project_name(self):
        assert (
            BaseProjectGenerator._normalize_project_name('My-Project') == 'my_project'
        )
        assert BaseProjectGenerator._normalize_project_name('some name') == 'some_name'
        assert (
            BaseProjectGenerator._normalize_project_name('already_good')
            == 'already_good'
        )

    def test_to_class_name(self):
        assert BaseProjectGenerator._to_class_name('my-project') == 'MyProject'
        assert BaseProjectGenerator._to_class_name('some_name') == 'SomeName'
        assert BaseProjectGenerator._to_class_name('single') == 'Single'

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseProjectGenerator()


class TestDeploymentProjectGenerator:
    """Test the concrete deployment generator."""

    def test_generate_local_p4p(self, generator, output_dir):
        path = generator.generate(
            name='test-project',
            interface_type='p4p_server',
            model_source='local',
            output_dir=str(output_dir),
        )
        assert path.exists()
        assert (path / 'deployment_config.yaml').exists()
        assert (path / 'env.json').exists()
        assert (path / 'README.md').exists()
        assert (path / 'model_definition.py').exists()
        assert not (path / 'docker').exists()
        assert not (path / 'k8s').exists()

    def test_generate_mlflow_fastapi(self, generator, output_dir):
        path = generator.generate(
            name='mlflow-proj',
            interface_type='fastapi',
            model_source='mlflow',
            output_dir=str(output_dir),
        )
        assert path.exists()
        assert (path / 'deployment_config.yaml').exists()
        assert (path / 'env.json').exists()
        assert (path / 'README.md').exists()
        # local model stub should NOT be generated for mlflow
        assert not (path / 'model_definition.py').exists()

    def test_generate_k2eg(self, generator, output_dir):
        path = generator.generate(
            name='k2eg-proj',
            interface_type='k2eg',
            model_source='local',
            output_dir=str(output_dir),
        )
        assert path.exists()
        assert (path / 'deployment_config.yaml').exists()

    def test_generate_with_docker(self, generator, output_dir):
        path = generator.generate(
            name='docker-proj',
            interface_type='p4p_server',
            model_source='local',
            include_docker=True,
            output_dir=str(output_dir),
        )
        assert (path / 'docker' / 'Dockerfile').exists()
        assert (path / 'docker' / 'docker_compose.yml').exists()

    def test_generate_with_kubernetes(self, generator, output_dir):
        path = generator.generate(
            name='k8s-proj',
            interface_type='fastapi',
            model_source='mlflow',
            include_kubernetes=True,
            output_dir=str(output_dir),
        )
        assert (path / 'k8s' / 'deployment.yaml').exists()
        assert (path / 'k8s' / 'service.yaml').exists()

    def test_generate_with_docker_and_kubernetes(self, generator, output_dir):
        path = generator.generate(
            name='full-proj',
            interface_type='p4p_server',
            model_source='local',
            include_docker=True,
            include_kubernetes=True,
            output_dir=str(output_dir),
        )
        assert (path / 'docker' / 'Dockerfile').exists()
        assert (path / 'k8s' / 'deployment.yaml').exists()

    def test_duplicate_name_raises(self, generator, output_dir):
        generator.generate(
            name='dup-proj',
            output_dir=str(output_dir),
        )
        with pytest.raises(FileExistsError):
            generator.generate(
                name='dup-proj',
                output_dir=str(output_dir),
            )

    def test_name_normalization(self, generator, output_dir):
        path = generator.generate(
            name='My Cool Project',
            output_dir=str(output_dir),
        )
        assert path.name == 'my_cool_project'

    def test_generated_yaml_is_valid(self, generator, output_dir):
        path = generator.generate(
            name='yaml-test',
            interface_type='p4p_server',
            model_source='local',
            output_dir=str(output_dir),
        )
        config_path = path / 'deployment_config.yaml'
        with open(config_path) as f:
            data = yaml.safe_load(f)
        assert 'deployment' in data
        assert 'modules' in data
        assert data['deployment']['type'] == 'continuous'

    def test_generated_yaml_has_correct_interface(self, generator, output_dir):
        for iface, expected_type in [
            ('p4p_server', 'interface.p4p_server'),
            ('fastapi', 'interface.fastapi_server'),
            ('k2eg', 'interface.k2eg'),
        ]:
            path = generator.generate(
                name=f'iface-{iface}',
                interface_type=iface,
                model_source='local',
                output_dir=str(output_dir),
            )
            with open(path / 'deployment_config.yaml') as f:
                data = yaml.safe_load(f)
            # Find the interface module
            iface_modules = [
                m
                for m in data['modules'].values()
                if m['type'].startswith('interface.')
            ]
            assert len(iface_modules) == 1
            assert iface_modules[0]['type'] == expected_type

    def test_generated_yaml_local_model(self, generator, output_dir):
        path = generator.generate(
            name='local-model-test',
            model_source='local',
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)
        model_config = data['modules']['model']['config']
        assert model_config['type'] == 'LocalModelGetter'
        assert 'model_path' in model_config['args']

    def test_generated_yaml_mlflow_model(self, generator, output_dir):
        path = generator.generate(
            name='mlflow-model-test',
            model_source='mlflow',
            output_dir=str(output_dir),
        )
        with open(path / 'deployment_config.yaml') as f:
            data = yaml.safe_load(f)
        model_config = data['modules']['model']['config']
        assert model_config['type'] == 'MlflowModelGetter'
        assert 'model_name' in model_config['args']

    def test_generated_env_json_mlflow(self, generator, output_dir):
        path = generator.generate(
            name='env-mlflow',
            model_source='mlflow',
            output_dir=str(output_dir),
        )
        import json

        with open(path / 'env.json') as f:
            data = json.load(f)
        assert 'MLFLOW_TRACKING_URI' in data

    def test_generated_env_json_local(self, generator, output_dir):
        path = generator.generate(
            name='env-local',
            model_source='local',
            output_dir=str(output_dir),
        )
        import json

        with open(path / 'env.json') as f:
            data = json.load(f)
        assert data == {}
