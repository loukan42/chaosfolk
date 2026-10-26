"""Exploration presets. These bound actions, not model tokens or spending."""
import argparse
import json


PRESETS = {
    "low": {"users": 2, "actions_per_user": 12, "max_parallel_users": 2},
    "medium": {"users": 4, "actions_per_user": 20, "max_parallel_users": 3},
    "high": {"users": 12, "actions_per_user": 40, "max_parallel_users": 3},
}


def plan(level):
    values = PRESETS[level]
    return {"level": level, **values, "max_user_actions": values["users"] * values["actions_per_user"],
            "token_limit": None, "includes_scout": False, "includes_replay": False}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk plan", description="Show an exploration budget without starting a run.")
    parser.add_argument("--level", choices=PRESETS, default="medium")
    parser.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = parser.parse_args(argv)
    result = plan(args.level)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.level}: {result['users']} simulated users, {result['actions_per_user']} actions per user, "
              f"up to {result['max_parallel_users']} running at once.")
        print(f"Pass --level {args.level} to launch, draw and sheets. "
              "Explicit --budget and --count override the preset.")
        print("The scout, analysis and model tokens are not capped by this plan. "
              "Actual cost depends on the agent host and model.")
    return 0
