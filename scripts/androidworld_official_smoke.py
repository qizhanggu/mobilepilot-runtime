"""Run one AndroidWorld task with its built-in RandomAgent and print a JSON summary.

This is an environment smoke test, not an evaluation result.  It verifies the
official environment, task initialization, action execution, and authoritative
reward path without requiring an external model provider.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from android_world import registry
from android_world.agents import random_agent
from android_world.env import env_launcher

from mobile_pilot.androidworld.download_cache import configure_from_environment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="ClockStopWatchRunning")
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--grpc-port", type=int, default=8554)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--perform-emulator-setup", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_from_environment()
    started = time.monotonic()
    env = None
    task = None
    try:
        env = env_launcher.load_and_setup_env(
            console_port=args.console_port,
            grpc_port=args.grpc_port,
            adb_path=args.adb_path,
            emulator_setup=args.perform_emulator_setup,
        )
        env.reset(go_home=True)
        task_registry = registry.TaskRegistry()
        tasks = task_registry.get_registry(task_registry.ANDROID_WORLD_FAMILY)
        task_type = tasks[args.task]
        random.seed(args.seed)
        task = task_type(task_type.generate_random_params())
        task.initialize_task(env)
        state_before = env.get_state(wait_to_stabilize=True)
        reward_before = task.is_successful(env)

        agent = random_agent.RandomAgent(env)
        result = agent.step(task.goal)
        reward_after = task.is_successful(env)

        summary = {
            "task": args.task,
            "goal": task.goal,
            "official_agent": agent.name,
            "agent_done": result.done,
            "official_reward_before": reward_before,
            "official_reward_after": reward_after,
            "screen_shape": list(state_before.pixels.shape),
            "ui_element_count": len(state_before.ui_elements),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    finally:
        if task is not None and env is not None:
            task.tear_down(env)
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
