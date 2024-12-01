from dotenv import load_dotenv
import os
import sys


def setup_logging():
    is_docker = os.environ.get("DOCKER_CONTAINER") == "1"
    debug_mode = os.environ.get("DEBUG") == "1"

    if is_docker:
        # In Docker, log to stdout/stderr for container logging
        log_file = None  # This will make logs go to stdout
    else:
        # Local development
        log_dir = "./logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "indexer.log")

    return log_file, debug_mode


def test_setup():
    """
    Test setup function that verifies the basic package installation and imports.
    Returns True if setup is successful, False otherwise.
    """
    try:
        print("\nVerifying package structure and environment:")

        # Check Python version
        import sys

        py_version = sys.version_info
        print(f"  ✓ Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")

        # Verify package structure
        import os

        src_dir = os.path.join(os.path.dirname(__file__), "src")
        if not os.path.exists(src_dir):
            raise ImportError("src directory not found")
        print("  ✓ Package structure verified")

        # Verify critical directories
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        print("  ✓ Log directory available")

        # Test package version and metadata
        import toml

        pyproject_path = os.path.join(os.path.dirname(__file__), "pyproject.toml")
        if os.path.exists(pyproject_path):
            with open(pyproject_path, "r") as f:
                pyproject = toml.load(f)
                version = pyproject["tool"]["poetry"]["version"]
                print("\n" + "=" * 50)
                print(f"  Testing BTC Stamps Indexer v{version}")
                print("=" * 50 + "\n")

        print("Verifying critical dependencies:")

        # Test critical package imports with versions
        import index_core

        print("  ✓ index_core")

        import bitcoinlib

        print(f"  ✓ bitcoinlib {bitcoinlib.__version__}")

        import pymysql

        print(f"  ✓ pymysql {pymysql.__version__}")

        import requests

        print(f"  ✓ requests {requests.__version__}")

        import boto3

        print(f"  ✓ boto3 {boto3.__version__}")

        import msgpack

        print(f"  ✓ msgpack {msgpack.version}")

        # Verify SSL/TLS capabilities
        import ssl

        print(f"  ✓ SSL/TLS support: {ssl.OPENSSL_VERSION}")

        # Check for required environment variables
        required_env = ["DOCKER_CONTAINER", "PYTHONUNBUFFERED"]
        missing_env = [env for env in required_env if not os.getenv(env)]
        if missing_env:
            print(f"\n⚠️  Warning: Missing environment variables: {', '.join(missing_env)}")
        else:
            print("  ✓ Environment variables verified")

        print("\nAll critical dependencies imported successfully ✨")
        sys.exit(0)

    except ImportError as e:
        sys.exit(f"\n❌ Import error: {str(e)}")
    except Exception as e:
        sys.exit(f"\n❌ Test setup failed: {str(e)}", file=sys.stderr)


def main():
    # Load .env file only if not in Docker
    if not os.environ.get("DOCKER_CONTAINER"):
        load_dotenv()

    # Setup logging before importing server
    log_file, debug_mode = setup_logging()

    import index_core.server as server

    # Initialize server with our logging configuration
    db = server.initialize(log_file=log_file, verbose=debug_mode)

    if db is None:
        print("Failed to connect to database", file=sys.stderr)
        sys.exit(1)

    server.start_all(db)


if __name__ == "__main__":
    main()
