import subprocess


def run_command(command):
    result = subprocess.run(command, shell=True)  # nosec
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    commands = [
        "poetry run black . --config=pyproject.toml",
        "poetry run flake8 .",
        "poetry run isort .",
        "poetry run task bandit",
        "poetry run mypy . --explicit-package-bases",
        "poetry run run_safety",
    ]

    for command in commands:
        run_command(command)


if __name__ == "__main__":
    main()
