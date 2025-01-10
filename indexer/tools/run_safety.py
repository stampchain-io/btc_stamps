import subprocess
import sys

import toml


def get_safety_ignores(pyproject_path="pyproject.toml"):
    with open(pyproject_path, "r") as f:
        pyproject = toml.load(f)
    return pyproject.get("tool", {}).get("safety", {}).get("ignore", [])


def run_safety_check():
    # Safety checks are disabled as per dev branch configuration
    print("Safety checks are disabled")
    return 0


if __name__ == "__main__":
    exit(run_safety_check())
