"""Astrolabe — hierarchical, read-only index for AI agents."""
from .core import (
    Config,
    build,
    DEFAULT_GROUP_PATTERNS,
    DEFAULT_SKIP_EXT,
    VERSION,
)

__all__ = ["Config", "build", "DEFAULT_GROUP_PATTERNS", "DEFAULT_SKIP_EXT", "VERSION"]
__version__ = VERSION