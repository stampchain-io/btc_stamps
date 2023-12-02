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
