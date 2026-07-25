"""Compatibility import for the canonical ATLAS ZERO EventBus.

Do not add a second EventBus implementation here.
"""

from ..events import EventBus

__all__ = ["EventBus"]
