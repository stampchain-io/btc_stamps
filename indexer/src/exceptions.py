#! /usr/bin/python3

class DatabaseError(Exception):
    pass

class ParseTransactionError(Exception):
    pass

class MessageError(Exception):
    pass

class DecodeError(MessageError):
    pass

class PushDataDecodeError(DecodeError):
    pass

class BTCOnlyError(MessageError):
    def __init__(self, msg, decodedTx=None):
        super(BTCOnlyError, self).__init__(msg)
        self.decodedTx = decodedTx

class DataConversionError(Exception):
    """Exception raised for errors in the data conversion process."""
    def __init__(self, message="Error occurred during data conversion"):
        self.message = message
        super().__init__(self.message)

class InvalidInputDataError(Exception):
    """Exception raised for invalid input data."""
    def __init__(self, message="Invalid input data"):
        self.message = message
        super().__init__(self.message)

class SerializationError(Exception):
    """Exception raised during serialization to JSON."""
    def __init__(self, message="Error occurred during JSON serialization"):
        self.message = message
        super().__init__(self.message)

class BlockAlreadyExistsError(Exception):
    """Exception raised when attempting to insert a block that already exists."""
    pass

class DatabaseInsertError(Exception):
    """Exception raised for errors that occur during database insert operations."""
    pass

class BlockUpdateError(Exception):
    """Exception raised for errors that occur during block update operations."""
    pass