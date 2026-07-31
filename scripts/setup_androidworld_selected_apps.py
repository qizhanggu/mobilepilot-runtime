"""Initialize a selected set of official AndroidWorld apps on an emulator.

This uses AndroidWorld's public ``setup.setup_apps`` API.  It is useful when
an unrelated app fails platform-specific setup (for example Joplin's FTS4
initialization on Windows) and must not block tasks that do not use that app.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mobile_pilot.androidworld.download_cache import configure_from_environment


DEFAULT_APPS = ("pro expense", "markor", "simple calendar pro", "simple sms messenger")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", action="append", choices=ALL_APP_NAMES, help="Repeat for each official app to set up.")
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--grpc-port", type=int, default=8554)
    return parser.parse_args()


def _available_apps() -> dict[str, type]:
    from android_world.env.setup_device import setup

    return {app.app_name: app for app in setup._APPS}


ALL_APP_NAMES = tuple(sorted(_available_apps()))


def main() -> None:
    args = parse_args()
    configure_from_environment()
    from android_world.env import env_launcher
    from android_world.env.setup_device import setup

    requested = tuple(args.app or DEFAULT_APPS)
    app_map = _available_apps()
    app_types = tuple(app_map[name] for name in requested)
    started = time.monotonic()
    env = None
    try:
        env = env_launcher.load_and_setup_env(
            console_port=args.console_port,
            grpc_port=args.grpc_port,
            adb_path=args.adb_path,
            emulator_setup=False,
        )
        setup.setup_apps(env, app_types)
        print(json.dumps({"configured_apps": requested, "elapsed_seconds": round(time.monotonic() - started, 3)}, ensure_ascii=False, sort_keys=True))
    finally:
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
