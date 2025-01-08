import subprocess

import toml


def get_safety_ignores(pyproject_path="pyproject.toml"):
    with open(pyproject_path, "r") as f:
        pyproject = toml.load(f)
    return pyproject.get("tool", {}).get("safety", {}).get("ignore", [])


def run_safety_check():
    ignores = get_safety_ignores()
    ignore_args = [f"--ignore={vuln}" for vuln in ignores]
    command = ["safety", "check", "--format", "text"] + ignore_args
    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    exit(run_safety_check())
