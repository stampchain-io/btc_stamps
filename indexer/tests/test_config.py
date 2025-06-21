import importlib
import os
import sys
import types
from typing import Any

import pytest

from tests.test_isolation_utils import IsolationManager


@pytest.fixture(autouse=True, scope="module")
def module_isolation():
    """Provide comprehensive isolation for this module."""
    rpc_env_vars = [
        "RPC_IP",
        "RPC_PORT",
        "RPC_USER",
        "RPC_PASSWORD",
        "RPC_SSL",
        "CP_RPC_IP",
        "CP_RPC_PORT",
        "CP_RPC_USER",
        "CP_RPC_PASSWORD",
        "CP_FALLBACK_MODE",
    ]

    with IsolationManager().isolate_sys_modules(["boto3"]).isolate_sys_path().isolate_environment(
        **{var: None for var in rpc_env_vars}
    ):
        # Ensure we import from the src directory
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

        # Explicitly stub out boto3 as a module with a client() factory
        _boto3_mod: Any = types.ModuleType("boto3")
        _boto3_mod.client = lambda *args, **kwargs: None  # type: ignore[attr-defined]
        sys.modules["boto3"] = _boto3_mod

        yield


# Import after setting up isolation
import exceptions


def reload_config():
    """
    Reload the config module to pick up current environment variables.
    """
    # Clear all config-related modules from cache
    modules_to_clear = []
    for module_name in sys.modules:
        if module_name == "config" or module_name.startswith("src.config"):
            modules_to_clear.append(module_name)
    
    for module_name in modules_to_clear:
        del sys.modules[module_name]
    
    return importlib.import_module("config")


def test_default_standard_rpc(monkeypatch):
    # Remove Quicknode and CP override to use defaults
    monkeypatch.delenv("QUICKNODE_URL", raising=False)
    monkeypatch.delenv("QUICKNODE_API_KEY", raising=False)
    monkeypatch.delenv("CP_RPC_URL", raising=False)
    # Remove additional CP variables that might affect config
    monkeypatch.delenv("CP_PRIMARY_NODE_URL", raising=False)
    monkeypatch.delenv("CP_FALLBACK_NODE_URL", raising=False)
    monkeypatch.delenv("CP_NODE_POOL", raising=False)
    # Remove TLS override
    monkeypatch.delenv("RPC_TLS", raising=False)
    # Remove any custom RPC credentials to fall back to defaults
    monkeypatch.delenv("RPC_USER", raising=False)
    monkeypatch.delenv("RPC_PASSWORD", raising=False)
    monkeypatch.delenv("RPC_IP", raising=False)
    monkeypatch.delenv("RPC_PORT", raising=False)

    config = reload_config()
    # Default standard RPC URL should be non-TLS with default creds
    assert config.RPC_URL == "http://rpc:rpc@127.0.0.1:8332"
    # Default Counterparty RPC URL should be set to the official endpoint
    assert config.CP_RPC_URL == "https://api.counterparty.io:4000/"


def test_standard_rpc_tls(monkeypatch):
    # Enable TLS via environment variable
    monkeypatch.setenv("RPC_TLS", "true")
    # Ensure Quicknode is disabled (no URL or API key)
    monkeypatch.delenv("QUICKNODE_URL", raising=False)
    monkeypatch.delenv("QUICKNODE_API_KEY", raising=False)
    # Remove any custom RPC credentials to ensure test uses defaults
    monkeypatch.delenv("RPC_USER", raising=False)
    monkeypatch.delenv("RPC_PASSWORD", raising=False)
    monkeypatch.delenv("RPC_IP", raising=False)
    monkeypatch.delenv("RPC_PORT", raising=False)
    monkeypatch.delenv("CP_RPC_URL", raising=False)

    config = reload_config()
    # Standard RPC URL should use https scheme when RPC_TLS is truthy
    assert config.RPC_URL.startswith("https://rpc:rpc@127.0.0.1:8332")


@pytest.mark.parametrize("endpoint,key", [("only-endpoint.example.com", None), (None, "onlyapikey123")])
def test_quicknode_partial_credentials_raise(monkeypatch, endpoint, key):
    # Set one Quicknode var without the other
    if endpoint is not None:
        monkeypatch.setenv("QUICKNODE_URL", endpoint)
    else:
        monkeypatch.delenv("QUICKNODE_ENDPOINT", raising=False)
    if key is not None:
        monkeypatch.setenv("QUICKNODE_API_KEY", key)
    else:
        monkeypatch.delenv("QUICKNODE_API_KEY", raising=False)

    # Importing config with partial Quicknode credentials must raise
    with pytest.raises(exceptions.ConfigurationError):
        reload_config()


def test_quicknode_full_credentials(monkeypatch):
    # Provide both Quicknode endpoint and API key
    monkeypatch.setenv("QUICKNODE_URL", "endpoint.example.com")
    monkeypatch.setenv("QUICKNODE_API_KEY", "secretkey")
    # Remove standard RPC credentials to ensure branch selection
    monkeypatch.delenv("RPC_USER", raising=False)
    monkeypatch.delenv("RPC_PASSWORD", raising=False)
    monkeypatch.delenv("RPC_IP", raising=False)
    monkeypatch.delenv("RPC_PORT", raising=False)

    config = reload_config()
    # The RPC_URL should combine the formatted endpoint and API key
    assert config.RPC_URL == "https://endpoint.example.com/secretkey/"
    # Standard RPC credentials should be disabled in Quicknode mode
    assert config.RPC_USER is None
    assert config.RPC_PASSWORD is None
    assert config.RPC_IP is None
    assert config.RPC_PORT is None
