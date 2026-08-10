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
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mobile_pilot.androidworld import MobilePilotAndroidWorldAgent, QwenSubgoalManager
from mobile_pilot.androidworld.download_cache import configure_from_environment
from mobile_pilot.androidworld.evaluation import is_official_success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="ClockStopWatchRunning")
    parser.add_argument("--mode", choices=("vision_only", "hybrid"), default="vision_only")
    parser.add_argument("--runtime-version", choices=("v1", "v2", "v2.1", "v2.2"), default="v2")
    parser.add_argument(
        "--progress-verifier-mode",
        choices=("off", "hybrid"),
        default="hybrid",
        help="V2.2 ablation: deterministic-only or event-triggered VLM Verifier.",
    )
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--trace-path", required=True)
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--grpc-port", type=int, default=8554)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--perform-emulator-setup", action="store_true")
    return parser.parse_args()


def main() -> None:
    # Delayed imports keep the control-flow helper unit-testable from the base
    # MobilePilot environment, which intentionally does not install AndroidWorld.
    from android_world import registry
    from android_world.env import env_launcher

    args = parse_args()
    configure_from_environment()
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
        if is_official_success(initial_reward):
            print(json.dumps({
                "task": args.task, "goal": task.goal, "mode": args.mode, "max_steps": args.max_steps,
                "runtime_version": args.runtime_version,
                "progress_verifier_mode": args.progress_verifier_mode,
                "agent_done": True, "agent_data": {"reason": "already_satisfied", "steps": 0},
                "initial_official_reward": initial_reward, "official_reward": initial_reward,
                "reward_by_step": [], "elapsed_seconds": round(time.monotonic() - started, 3),
                "trace_path": args.trace_path,
            }, ensure_ascii=False, sort_keys=True))
            return
        agent = MobilePilotAndroidWorldAgent(
            env,
            mode=args.mode,
            max_steps=args.max_steps,
            trace_path=args.trace_path,
            runtime_version=args.runtime_version,
            progress_verifier_mode=args.progress_verifier_mode,
            subgoal_manager=(
                QwenSubgoalManager() if args.runtime_version == "v2.2" else None
            ),
        )
        result, rewards = _run_agent_loop(
            agent,
            task.goal,
            lambda: float(task.is_successful(env)),
            max_steps=args.max_steps,
        )
        print(json.dumps({
            "task": args.task, "goal": task.goal, "mode": args.mode, "max_steps": args.max_steps,
            "runtime_version": args.runtime_version,
            "progress_verifier_mode": args.progress_verifier_mode,
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


def _should_retry_rejected_completion(
    data: dict[str, object], *, max_steps: int, already_rejected: bool
) -> bool:
    """Allow one official rejection when at least one action step remains.

    A completion proposal is not an executed UI action, therefore it must not
    consume an action-step slot.  Limiting the continuation to one proposal
    prevents a model that repeatedly self-completes from creating an unbounded
    runner loop.
    """
    if already_rejected or data.get("reason") != "actor_proposed_complete":
        return False
    steps = data.get("steps")
    return isinstance(steps, int) and steps < max_steps


def _run_agent_loop(
    agent: Any,
    goal: str,
    official_reward: Callable[[], float],
    *,
    max_steps: int,
) -> tuple[Any, list[float]]:
    """Run until official success or a bounded terminal Agent result.

    Completion proposals do not execute an Android action, so the single
    allowed rejection continues the same action budget rather than consuming a
    synthetic extra step.
    """
    completion_rejection_used = False
    rewards: list[float] = []
    while True:
        result = agent.step(goal)
        reward = official_reward()
        rewards.append(reward)
        if is_official_success(reward):
            _record_official_reward(agent, reward, terminal=True)
            return result, rewards
        if not result.done:
            _record_official_reward(agent, reward, terminal=False)
            continue
        if _should_retry_rejected_completion(
            result.data,
            max_steps=max_steps,
            already_rejected=completion_rejection_used,
        ):
            _record_official_reward(agent, reward, terminal=False)
            agent.reject_completion_proposal(
                "AndroidWorld official reward remained below full success (1.0)."
            )
            completion_rejection_used = True
            continue
        _record_official_reward(agent, reward, terminal=True)
        return result, rewards


def _record_official_reward(agent: Any, reward: float, *, terminal: bool) -> None:
    callback = getattr(agent, "record_official_reward", None)
    if callable(callback):
        callback(reward, terminal=terminal)


if __name__ == "__main__":
    main()
