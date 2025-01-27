import subprocess


def run_command(command):
    print(f"\nRunning: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)  # nosec
    if result.returncode != 0:
        print("Command failed with output:")
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    else:
        print("Command succeeded")
        if result.stdout:
            print(result.stdout)


def main():
    commands = [
        "poetry run black . --config=pyproject.toml",
        "poetry run flake8 .",
        "poetry run isort .",
        "poetry run task bandit",
        "poetry run mypy . --explicit-package-bases",
        "poetry run run_safety",
        "cargo fmt --version",
        "cargo fmt -- --check --manifest-path src/rust_parser/Cargo.toml",
        "rustup show",
    ]

    for command in commands:
        run_command(command)


if __name__ == "__main__":
    main()
