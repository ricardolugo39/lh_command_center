import os
import runpy
from pathlib import Path
from typing import Iterable

from dotenv import dotenv_values
from flask import current_app, has_app_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ENV_PATH = PROJECT_ROOT / ".env"
PROJECT_CONFIG_PATH = PROJECT_ROOT / "config.py"

# Backward-compatible location used by the original development installation.
# It is derived from the user home rather than embedding a developer username.
LEGACY_CREDENTIALS_DIR = (
    Path.home() / "Documents" / "CommercialCommandCenter" / "credentials"
)
LEGACY_ENV_PATH = LEGACY_CREDENTIALS_DIR / ".env"


def resolve_settings(names: Iterable[str]) -> tuple[dict[str, str], dict[str, Path | None]]:
    """Resolve configuration without requiring one launch mechanism.

    Precedence: process environment, Flask configuration, explicit env file,
    project .env, legacy development .env, and project config.py.
    """
    requested = tuple(names)
    values: dict[str, str] = {}
    sources: dict[str, Path | None] = {}

    for name in requested:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            values[name] = value
            sources[name] = None

    if has_app_context():
        for name in requested:
            if name in values:
                continue
            value = str(current_app.config.get(name, "") or "").strip()
            if value:
                values[name] = value
                sources[name] = PROJECT_CONFIG_PATH

    for path in _environment_files():
        if not path.is_file():
            continue
        file_values = dotenv_values(path)
        for name in requested:
            if name in values:
                continue
            value = str(file_values.get(name, "") or "").strip()
            if value:
                values[name] = value
                sources[name] = path

    if PROJECT_CONFIG_PATH.is_file():
        namespace = runpy.run_path(str(PROJECT_CONFIG_PATH))
        config = {
            key: value
            for key, value in namespace.items()
            if key.isupper()
        }
        config_class = namespace.get("Config")
        if config_class:
            config.update({
                name: getattr(config_class, name)
                for name in dir(config_class)
                if name.isupper()
            })
        for name in requested:
            if name in values:
                continue
            value = str(config.get(name, "") or "").strip()
            if value:
                values[name] = value
                sources[name] = PROJECT_CONFIG_PATH

    return values, sources


def resolve_file_path(value: str, source: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path

    candidates = []
    if source is not None:
        candidates.append(source.parent / path)
    candidates.extend((
        PROJECT_ROOT / path,
        LEGACY_CREDENTIALS_DIR / path,
        Path.cwd() / path,
    ))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve() if candidates else path.resolve()


def _environment_files() -> tuple[Path, ...]:
    explicit = os.getenv("COMMERCIAL_COMMAND_CENTER_ENV_FILE", "").strip()
    paths = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.extend((PROJECT_ENV_PATH, LEGACY_ENV_PATH))
    # Preserve precedence while avoiding duplicate reads.
    return tuple(dict.fromkeys(path.resolve() for path in paths))
