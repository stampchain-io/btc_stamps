class ConfigurationError(Exception):
    """Raised when there is an error in the configuration."""

    pass


class BackendRPCError(Exception):
    """Raised when there is an error communicating with the backend RPC."""

    pass


class DatabaseError(Exception):
    pass


class DecodeError(Exception):
    pass


class BlockAlreadyExistsError(Exception):
    pass


class BlockUpdateError(Exception):
    pass


class BTCOnlyError(Exception):
    pass


class DatabaseInsertError(Exception):
    pass


class ParserError(Exception):
    """Raised when there is an error parsing transactions or blocks."""

    pass
