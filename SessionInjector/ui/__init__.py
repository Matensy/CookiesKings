"""Presentation layer: framework-agnostic renderers and the Tkinter GUI."""
from .dashboard import render_analysis, render_session

__all__ = ["render_analysis", "render_session"]

# The GUI is imported lazily via ``from SessionInjector.ui.gui import main`` so
# that importing this package never requires a display / Tk to be present.
