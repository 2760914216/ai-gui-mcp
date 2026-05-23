"""YAML configuration loader.

Loads config.yaml and exposes structured access to server, input, screen, and
behavior settings. Uses _deep_get() for safe dotted-path access with defaults.
"""

from pathlib import Path
from typing import Any

import yaml


def _deep_get(d: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Safely traverse a nested dict using dotted path notation.

    Example:
        _deep_get(config, "input.uinput.device_name", "default-name")
    """
    keys = key_path.split(".")
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return default
    return d


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load YAML configuration from a file path.

    Returns the parsed config dict, or an empty dict if the file is missing.
    """
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
