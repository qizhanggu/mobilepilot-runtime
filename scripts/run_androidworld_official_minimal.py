"""Launch AndroidWorld's upstream minimal runner on Windows without patching it.

The pinned upstream ``minimal_task_runner.py`` discovers ADB while its module is
being imported.  Its discovery paths are Unix-style and omit ``.exe``; command
line ``--adb_path`` is therefore parsed too late on Windows.  This wrapper only
bridges that import-time discovery check, then delegates to the unmodified
upstream script with an explicit ADB executable path.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANDROIDWORLD_ROOT = REPOSITORY_ROOT / ".local" / "android_world"
DEFAULT_ADB_PATH = (
    Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / "adb.exe"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--androidworld-root", type=Path, default=DEFAULT_ANDROIDWORLD_ROOT)
    parser.add_argument("--adb-path", type=Path, default=DEFAULT_ADB_PATH)
    parser.add_argument("--perform-emulator-setup", action="store_true")
    return parser.parse_args()


def _is_upstream_windows_adb_probe(path: object) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return normalized.endswith("/android/sdk/platform-tools/adb")


def main() -> None:
    args = parse_args()
    runner = args.androidworld_root / "minimal_task_runner.py"
    if not runner.is_file():
        raise FileNotFoundError(f"AndroidWorld minimal runner not found: {runner}")
    if not args.adb_path.is_file():
        raise FileNotFoundError(f"ADB executable not found: {args.adb_path}")

    original_isfile = os.path.isfile

    def isfile_with_windows_bootstrap(path: object) -> bool:
        return _is_upstream_windows_adb_probe(path) or original_isfile(path)

    os.path.isfile = isfile_with_windows_bootstrap
    sys.argv = [
        str(runner),
        f"--task={args.task}",
        f"--console_port={args.console_port}",
        f"--adb_path={args.adb_path}",
    ]
    if args.perform_emulator_setup:
        sys.argv.append("--perform_emulator_setup")
    runpy.run_path(str(runner), run_name="__main__")


if __name__ == "__main__":
    main()
