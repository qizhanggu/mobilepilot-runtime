"""Run one AndroidWorld task with the generic MobilePilot multi-step Agent.

The script deliberately has no task-specific action sequence. AndroidWorld's
``task.is_successful`` remains the only final success signal printed here.
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
from android_world.env import env_launcher

from mobile_pilot.androidworld import MobilePilotAndroidWorldAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="ClockStopWatchRunning")
    parser.add_argument("--mode", choices=("vision_only", "hybrid"), default="vision_only")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--trace-path", required=True)
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--grpc-port", type=int, default=8554)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--perform-emulator-setup", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_steps < 1:
        raise ValueError("--max-steps must be positive")
    started = time.monotonic()
    env = task = None
    try:
        env = env_launcher.load_and_setup_env(
            console_port=args.console_port,
            grpc_port=args.grpc_port,
            adb_path=args.adb_path,
            emulator_setup=args.perform_emulator_setup,
        )
        env.reset(go_home=True)
        task_type = registry.TaskRegistry().get_registry(registry.TaskRegistry.ANDROID_WORLD_FAMILY)[args.task]
        random.seed(args.seed)
        task = task_type(task_type.generate_random_params())
        task.initialize_task(env)
        initial_reward = float(task.is_successful(env))
        if initial_reward > 0:
            print(json.dumps({
                "task": args.task, "goal": task.goal, "mode": args.mode, "max_steps": args.max_steps,
                "agent_done": True, "agent_data": {"reason": "already_satisfied", "steps": 0},
                "initial_official_reward": initial_reward, "official_reward": initial_reward,
                "reward_by_step": [], "elapsed_seconds": round(time.monotonic() - started, 3),
                "trace_path": args.trace_path,
            }, ensure_ascii=False, sort_keys=True))
            return
        agent = MobilePilotAndroidWorldAgent(env, mode=args.mode, max_steps=args.max_steps, trace_path=args.trace_path)
        result = None
        rewards: list[float] = []
        for _ in range(args.max_steps):
            result = agent.step(task.goal)
            reward = float(task.is_successful(env))
            rewards.append(reward)
            if result.done or reward > 0:
                break
        print(json.dumps({
            "task": args.task, "goal": task.goal, "mode": args.mode, "max_steps": args.max_steps,
            "agent_done": result.done if result else True, "agent_data": result.data if result else {},
            "initial_official_reward": initial_reward,
            "official_reward": rewards[-1] if rewards else float(task.is_successful(env)),
            "reward_by_step": rewards, "elapsed_seconds": round(time.monotonic() - started, 3),
            "trace_path": args.trace_path,
        }, ensure_ascii=False, sort_keys=True))
    finally:
        if task is not None and env is not None:
            task.tear_down(env)
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
