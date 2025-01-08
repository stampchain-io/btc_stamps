import subprocess
import sys

import toml


def get_safety_ignores(pyproject_path="pyproject.toml"):
    with open(pyproject_path, "r") as f:
        pyproject = toml.load(f)
    return pyproject.get("tool", {}).get("safety", {}).get("ignore", [])


def run_safety_check():
    ignores = get_safety_ignores()
    ignore_args = [f"--ignore={vuln}" for vuln in ignores]
    command = ["safety", "check", "--output", "text"] + ignore_args
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode
    except Exception as e:
        print(f"Error running safety check: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit(run_safety_check())
