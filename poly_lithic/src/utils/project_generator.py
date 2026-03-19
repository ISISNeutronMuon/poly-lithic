"""
Project generators using Jinja2 templates.

Provides an abstract base class for project generation and a concrete
DeploymentProjectGenerator for scaffolding poly-lithic deployment projects.
A ReadyModelProjectGenerator extends the deployment generator to introspect
an existing model and pre-populate variable mappings.
"""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from poly_lithic.src.utils.model_introspector import ModelIntrospector, ModelMetadata


class BaseProjectGenerator(ABC):
    """Abstract base class for project generators.

    Subclasses must implement ``_get_template_dir`` and ``generate``.
    Shared rendering and naming helpers are provided here.
    """

    def __init__(self):
        templates_dir = self._get_template_dir()
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @abstractmethod
    def _get_template_dir(self) -> Path:
        """Return the path to the Jinja2 templates directory."""

    @abstractmethod
    def generate(self, **kwargs) -> Path:
        """Generate a project and return its path."""

    def _render_template(self, template_name: str, output_path: Path, context: dict):
        """Render a Jinja2 template and write it to *output_path*."""
        template = self.env.get_template(template_name)
        content = template.render(**context)
        output_path.write_text(content)

    @staticmethod
    def _normalize_project_name(name: str) -> str:
        """Normalize *name* to a valid snake_case identifier."""
        return name.replace('-', '_').replace(' ', '_').lower()

    @staticmethod
    def _to_class_name(name: str) -> str:
        """Convert *name* to PascalCase."""
        parts = name.replace('-', ' ').replace('_', ' ').split()
        return ''.join(word.capitalize() for word in parts)


class DeploymentProjectGenerator(BaseProjectGenerator):
    """Generate a poly-lithic deployment project from templates."""

    def _get_template_dir(self) -> Path:
        return Path(__file__).parent.parent.parent / 'templates' / 'deployment'

    def generate(
        self,
        name: str,
        interface_type: str = 'p4p_server',
        model_source: str = 'local',
        author: str = '',
        description: str = '',
        output_dir: str = '.',
        include_docker: bool = False,
        include_kubernetes: bool = False,
    ) -> Path:
        """Generate a deployment project.

        Args:
            name: Project name (will be normalised to snake_case).
            interface_type: One of ``p4p_server``, ``fastapi``, ``k2eg``.
            model_source: One of ``local``, ``mlflow``.
            author: Author name.
            description: Short project description.
            output_dir: Parent directory for the generated project.
            include_docker: Whether to include Docker files.
            include_kubernetes: Whether to include Kubernetes manifests.

        Returns:
            Path to the generated project directory.
        """
        project_name = self._normalize_project_name(name)
        class_name = self._to_class_name(name)

        project_path = Path(output_dir).expanduser().resolve() / project_name
        if project_path.exists():
            raise FileExistsError(f'Directory {project_path} already exists')

        project_path.mkdir(parents=True)

        context = {
            'project_name': project_name,
            'class_name': class_name,
            'interface_type': interface_type,
            'model_source': model_source,
            'author': author,
            'description': description or f'A poly-lithic deployment project',
            'year': datetime.now().year,
            'include_docker': include_docker,
            'include_kubernetes': include_kubernetes,
            'docker_image': 'matindocker/poly-lithic:base-latest',
        }

        # Core files
        self._render_template(
            'deployment_config.yaml.j2',
            project_path / 'deployment_config.yaml',
            context,
        )
        self._render_template('env.json.j2', project_path / 'env.json', context)
        self._render_template('README.md.j2', project_path / 'README.md', context)

        if model_source == 'local':
            self._render_template(
                'model_definition.py.j2',
                project_path / 'model_definition.py',
                context,
            )

        # Optional Docker files
        if include_docker:
            docker_path = project_path / 'docker'
            docker_path.mkdir()
            self._render_template(
                'docker/Dockerfile.j2', docker_path / 'Dockerfile', context
            )
            self._render_template(
                'docker/docker_compose.yml.j2',
                docker_path / 'docker_compose.yml',
                context,
            )

        # Optional Kubernetes manifests
        if include_kubernetes:
            k8s_path = project_path / 'k8s'
            k8s_path.mkdir()
            self._render_template(
                'k8s/deployment.yaml.j2', k8s_path / 'deployment.yaml', context
            )
            self._render_template(
                'k8s/service.yaml.j2', k8s_path / 'service.yaml', context
            )

        return project_path


class ReadyModelProjectGenerator(BaseProjectGenerator):
    """Generate a deployment project from an existing model definition.

    Introspects the model to extract input/output variable names and
    pre-populates the deployment configuration with correct mappings.
    """

    def _get_template_dir(self) -> Path:
        return Path(__file__).parent.parent.parent / 'templates' / 'deployment'

    def generate(
        self,
        name: str,
        model_file: str | None = None,
        interface_type: str = 'p4p_server',
        author: str = '',
        description: str = '',
        output_dir: str = '.',
        include_docker: bool = False,
        include_kubernetes: bool = False,
        factory_class: str = 'ModelFactory',
        metadata: ModelMetadata | None = None,
    ) -> Path:
        """Generate a deployment project pre-populated from a model file.

        Args:
            name: Project name (will be normalised to snake_case).
            model_file: Path to the model_definition.py to introspect.
                Can be ``None`` when *metadata* is supplied directly.
            interface_type: One of ``p4p_server``, ``fastapi``, ``k2eg``.
            author: Author name.
            description: Short project description.
            output_dir: Parent directory for the generated project.
            include_docker: Whether to include Docker files.
            include_kubernetes: Whether to include Kubernetes manifests.
            factory_class: Name of the factory class inside the model file.
            metadata: Pre-built :class:`ModelMetadata` (e.g. from a JSON
                sample file).  When provided, *model_file* introspection is
                skipped.

        Returns:
            Path to the generated project directory.
        """
        if metadata is None:
            if model_file is None:
                raise ValueError("Either 'model_file' or 'metadata' must be provided")
            introspector = ModelIntrospector(model_file, factory_class)
            metadata = introspector.introspect()

        project_name = self._normalize_project_name(name)
        class_name = self._to_class_name(name)

        project_path = Path(output_dir).expanduser().resolve() / project_name
        if project_path.exists():
            raise FileExistsError(f'Directory {project_path} already exists')

        project_path.mkdir(parents=True)

        context = {
            'project_name': project_name,
            'class_name': class_name,
            'interface_type': interface_type,
            'model_source': 'local',
            'author': author,
            'description': description or 'A poly-lithic deployment project',
            'year': datetime.now().year,
            'include_docker': include_docker,
            'include_kubernetes': include_kubernetes,
            'docker_image': 'matindocker/poly-lithic:base-latest',
            'input_variables': metadata.input_variables,
            'output_variables': metadata.output_variables,
            'factory_class': factory_class,
        }

        # Core files
        self._render_template(
            'deployment_config.yaml.j2',
            project_path / 'deployment_config.yaml',
            context,
        )
        self._render_template('env.json.j2', project_path / 'env.json', context)
        self._render_template('README.md.j2', project_path / 'README.md', context)

        # Copy the real model definition if one was provided; otherwise render stub
        if model_file:
            shutil.copy2(
                str(Path(model_file).resolve()), project_path / 'model_definition.py'
            )
        else:
            self._render_template(
                'model_definition.py.j2',
                project_path / 'model_definition.py',
                context,
            )

        # Optional Docker files
        if include_docker:
            docker_path = project_path / 'docker'
            docker_path.mkdir()
            self._render_template(
                'docker/Dockerfile.j2', docker_path / 'Dockerfile', context
            )
            self._render_template(
                'docker/docker_compose.yml.j2',
                docker_path / 'docker_compose.yml',
                context,
            )

        # Optional Kubernetes manifests
        if include_kubernetes:
            k8s_path = project_path / 'k8s'
            k8s_path.mkdir()
            self._render_template(
                'k8s/deployment.yaml.j2', k8s_path / 'deployment.yaml', context
            )
            self._render_template(
                'k8s/service.yaml.j2', k8s_path / 'service.yaml', context
            )

        return project_path
