# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Poly-Lithic'
copyright = '2025, Matuesz Leputa - ISIS Neutron and Muon Source at RAL - Science and Technology Facilities Council'
author = 'Matuesz Leputa'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'sphinxemoji.sphinxemoji',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo'
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Optional theme
html_permalinks_icon = '<span>🔗</span>'
html_theme = 'sphinxawesome_theme'  # or 'alabaster', 'sphinx_rtd_theme', etc.
html_static_path = ['_static']

autodoc_member_order = 'bysource'  # show functions in source order
autodoc_typehints = 'description'  # show type hints in function descriptions
