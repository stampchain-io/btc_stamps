class ConfigurationError(Exception):
    """Raised when there is an error in the configuration."""

    pass


class BackendRPCError(Exception):
    """Raised when there is an error communicating with the backend RPC."""

    pass
