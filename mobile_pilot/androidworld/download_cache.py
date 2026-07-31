"""Optional local cache for AndroidWorld's official GCS setup artifacts.

Some Windows Python TLS stacks fail against Google Cloud Storage while the
system curl client succeeds.  This module changes only the download transport:
the URLs and AndroidWorld installation/setup code remain official.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Callable


_A11Y_URL = "https://storage.googleapis.com/android_env-tasks/2024.05.13-accessibility_forwarder.apk"
_APP_URL_PREFIX = "https://storage.googleapis.com/gresearch/android_world/"


def configure_official_download_cache(cache_dir: str | Path) -> None:
    """Patch AndroidWorld runtime download hooks to use a persistent curl cache."""
    cache = Path(cache_dir)
    from android_env.wrappers import a11y_grpc_wrapper
    from android_world.env.setup_device import apps

    a11y_grpc_wrapper._get_accessibility_forwarder_apk = lambda: _download(  # type: ignore[attr-defined]
        _A11Y_URL, cache / "2024.05.13-accessibility_forwarder.apk"
    ).read_bytes()
    apps.download_app_data = lambda file_name: str(  # type: ignore[assignment]
        _download(_APP_URL_PREFIX + _safe_name(file_name), cache / _safe_name(file_name))
    )


def configure_from_environment() -> bool:
    """Enable the workaround only when the caller explicitly opts in."""
    configured = os.getenv("MOBILEPILOT_ANDROIDWORLD_DOWNLOAD_CACHE")
    if not configured:
        return False
    configure_official_download_cache(configured)
    return True


def _download(url: str, destination: Path, runner: Callable[..., object] = subprocess.run) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    runner(
        ["curl.exe", "--fail", "--location", "--retry", "1", "--connect-timeout", "20", "--output", str(destination), url],
        check=True,
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Official AndroidWorld download produced no file: {destination}")
    return destination


def _safe_name(file_name: str) -> str:
    name = Path(file_name).name
    if not name or name != file_name:
        raise ValueError(f"AndroidWorld download file name must be a plain name: {file_name!r}")
    return name
