import subprocess
import sys
import toml
from pathlib import Path


def get_safety_ignores(pyproject_path="pyproject.toml"):
    try:
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
        return pyproject.get("tool", {}).get("safety", {}).get("ignore", [])
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}")
        return []


def check_safety_installed():
    try:
        result = subprocess.run(["safety", "--version"], check=True, capture_output=True, text=True)
        print(f"Safety version: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Safety is not installed or not working: {e}")
        return False


def run_safety_check():
    print("Starting safety check...")

    if not check_safety_installed():
        return 1

    try:
        # Get the project root directory (where pyproject.toml is located)
        project_root = Path(__file__).parent.parent
        pyproject_path = project_root / "pyproject.toml"

        print(f"Reading safety ignores from: {pyproject_path}")
        ignores = get_safety_ignores(str(pyproject_path))
        print(f"Found {len(ignores)} safety ignores: {ignores}")

        ignore_args = [f"--ignore={vuln}" for vuln in ignores]
        command = ["safety", "check"] + ignore_args

        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)

        if result.stdout:
            print("Safety check output:")
            print(result.stdout)

        if result.stderr:
            print("Safety check errors:")
            print(result.stderr, file=sys.stderr)

        return result.returncode

    except subprocess.CalledProcessError as e:
        print(f"Safety check failed with return code {e.returncode}")
        if e.stdout:
            print("Output:", e.stdout)
        if e.stderr:
            print("Error:", e.stderr, file=sys.stderr)
        return e.returncode
    except Exception as e:
        print(f"Unexpected error running safety check: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_safety_check())
