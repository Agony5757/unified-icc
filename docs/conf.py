"""Sphinx configuration for unified-icc documentation."""

import sys
from pathlib import Path

# Add source directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Project information
project = "Unified ICC"
copyright = "2024-2026, Agony5757"
author = "Agony5757"
version = "0.1.0"
release = "0.1.0"

# Extensions
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.graphviz",
    "sphinx.ext.inheritance_diagram",
    "myst_parser",
]

# Templates
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Source files
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# HTML output
html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "github_url": "https://github.com/Agony5757/unified-icc",
    "repository_url": "https://github.com/Agony5757/unified-icc",
    "use_repository_button": True,
    "use_issues_button": True,
    "use_edit_page_button": True,
    "home_page_in_toc": True,
    "show_navbar_depth": 2,
    "show_toc_level": 2,
    "navigation_depth": 3,
}

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "show-inheritance": True,
}

autodoc_typehints = "description"
autodoc_class_signature = "separated"

# Napoleon settings (Google/NumPy style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "tmux": ("https://man.openbsd.org/cgi-bin/man.1.cgi?query=tmux&section=1", None),
}

# Graphviz
graphviz_output_format = "svg"
inheritance_graph_attrs = {
    "rankdir": "TB",
    "splines": "ortho",
    "nodesep": "0.5",
    "ranksep": "0.5",
}

# Todo
todo_include_todos = True

# Coverage
