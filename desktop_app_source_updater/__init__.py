# Kept in step with pyproject.toml and CITATION.cff by TestVersionConsistency.
# pyproject.toml stays the packaging source of truth because release.yml reads
# it to verify the tag; this marker is what survives into an installed app.
# A vendored copy of this package ships without pyproject.toml, so without it
# there is no way to tell which updater a user is actually running.
__version__ = "0.3.0"

from .core import (
    DEFAULT_BLOCKED_PATH_NAMES,
    DEFAULT_BLOCKED_PATH_PREFIXES,
    DEFAULT_BLOCKED_PATH_SUFFIXES,
    DEFAULT_CHECK_INTERVAL_SECONDS,
    UpdateConfig,
    UpdateError,
    StartupUpdateResult,
    format_update_message,
    read_python_assignment_version,
    run_startup_update,
)

__all__ = [
    "__version__",
    "DEFAULT_BLOCKED_PATH_NAMES",
    "DEFAULT_BLOCKED_PATH_PREFIXES",
    "DEFAULT_BLOCKED_PATH_SUFFIXES",
    "DEFAULT_CHECK_INTERVAL_SECONDS",
    "UpdateConfig",
    "UpdateError",
    "StartupUpdateResult",
    "format_update_message",
    "read_python_assignment_version",
    "run_startup_update",
]
