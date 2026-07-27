"""LM-Gambit web backend.

Wraps the existing ``.core`` diagnostic engine in a FastAPI application so the
React frontend can drive it. The engine itself is untouched: providers, the
runner and the markdown reporting pipeline behave exactly as they do for the
``auto-test.py`` CLI.
"""

__version__ = "2.0.0"
