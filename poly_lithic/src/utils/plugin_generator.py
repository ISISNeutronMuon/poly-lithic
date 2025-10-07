"""
Plugin project generator using Jinja2 templates.
"""

from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape


class PluginGenerator:
    """Generate plugin projects from Jinja2 templates."""
    
    def __init__(self):
        """Initialize the generator with template environment."""
        # Get the templates directory
        templates_dir = Path(__file__).parent.parent.parent / 'templates' / 'plugin'
        
        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    
    def generate(
        self,
        name: str,
        author: str = '',
        email: str = '',
        description: str = '',
        output_dir: str = '.',
        license: str = 'MIT',
    ) -> Path:
        """
        Generate a plugin project from templates.
        
        Args:
            name: Plugin package name (will be normalized to snake_case)
            author: Author name
            email: Author email
            description: Plugin description
            output_dir: Output directory for the project
            license: License type
            
        Returns:
            Path to the generated project
        """
        # Normalize names
        package_name = self._normalize_package_name(name)
        class_name = self._to_class_name(name)
        
        # Create project directory
        project_path = Path(output_dir).expanduser().resolve() / package_name
        if project_path.exists():
            raise FileExistsError(f"Directory {project_path} already exists")
        
        project_path.mkdir(parents=True)
        
        # Create package directory
        src_path = project_path / package_name
        src_path.mkdir()
        
        # Create tests directory
        test_path = project_path / 'tests'
        test_path.mkdir()
        
        # Template context
        context = {
            'package_name': package_name,
            'class_name': class_name,
            'author': author,
            'email': email,
            'description': description or f"A poly_lithic plugin package",
            'license': license,
            'year': datetime.now().year,
        }
        
        # Generate files from templates
        self._render_template('pyproject.toml.j2', project_path / 'pyproject.toml', context)
        self._render_template('README.md.j2', project_path / 'README.md', context)
        self._render_template('__init__.py.j2', src_path / '__init__.py', context)
        self._render_template('plugins.py.j2', src_path / 'plugins.py', context)
        self._render_template('test_plugins.py.j2', test_path / 'test_plugins.py', context)
        self._render_template('gitignore.j2', project_path / '.gitignore', context)
        
        # Create empty __init__.py in tests
        (test_path / '__init__.py').write_text('')
        
        return project_path
    
    def _render_template(self, template_name: str, output_path: Path, context: dict):
        """Render a template and write to file."""
        template = self.env.get_template(template_name)
        content = template.render(**context)
        output_path.write_text(content)
    
    @staticmethod
    def _normalize_package_name(name: str) -> str:
        """Normalize package name to valid Python package name."""
        return name.replace('-', '_').replace(' ', '_').lower()
    
    @staticmethod
    def _to_class_name(name: str) -> str:
        """Convert package name to PascalCase class name."""
        parts = name.replace('-', ' ').replace('_', ' ').split()
        return ''.join(word.capitalize() for word in parts)