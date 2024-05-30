import subprocess


def main():
    subprocess.run(["pre-commit", "install"], check=True)
