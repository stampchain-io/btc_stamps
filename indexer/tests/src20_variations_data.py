src20_variations_data = [
  {
    "description": "Test case for a basic SRC-20 token deployment",
    "src20JsonString": {
      "p": "SRC-20",
      "op": "DEPLOY",
      "tick": "TEST",
      "deci": 8,
      "lim": 1000000,
      "max": 1000000000
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "SRC-20 token deployment successful"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, no user balance",
    "src20JsonString": {
      "p": "SRC-20",
      "op": "TRANSFER",
      "tick": "TEST",
      "from": "1SourceAddr",
      "to": "1DestAddr",
      "amt": 5000
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "SRC-20 token transfer, no user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token minting, no prior deployment",
    "src20JsonString": {
      "p": "SRC-20",
      "op": "MINT",
      "tick": "TEST",
      "to": "1DestAddr",
      "amt": 10000
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "SRC-20 token minting failed, token not deployed"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for invalid SRC-20 operation",
    "src20JsonString": {
      "p": "SRC-20",
      "op": "INVALID_OP",
      "tick": "TESTTOKEN"
    },
    "expectedOutcome": {
      "stamp_success": False,
      "src20_success": False,
      "message": "Invalid SRC-20 operation"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for TRANSFER op",
    "src20JsonString": {
      "op": "TRANSFER",
      "p": "SRC-20",
      "tick": "SPECIALTOKEN",
      "from": "1SpecialSourceAddr",
      "to": "1SpecialDestAddr",
      "amt": 100000
    },
    "expectedOutcome": {
      "stamp_success": False,
      "src20_success": False,
      "message": "Failure, invalid Tick Length",
      "dbChanges": {
        "balances": [
          {
            "address": "1SpecialDestAddr",
            "tick": "SPECIALTOKEN",
            "amt": 100000
          }
        ]
      }
    },
    "source": "1SpecialSourceAddr",
    "destination": "1SpecialDestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token minting, with prior deployment",
    "src20JsonString": {
      "p": "SRC-20",
      "op": "MINT",
      "tick": "KEVIN",
      "amt": 100000
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed, expect success/success"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },

  {
    "description": "Test case for SRC-20 token deployment, scenario No.1 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "1.0"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "Token not previously deployed, expect success/fail - UPDATE SRC20 Results"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.1 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": 1.0
    },
    "expectedOutcome": {
      "stamp_success": False,
      "src20_success": False,
      "message": "token not previously deployed, expect fail/fail - OK "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.1 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "1.0"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, expect success/FAIL - UPDATE SRC20 Results"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.1 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": 1.0
    },
    "expectedOutcome": {
      "stamp_success": False,
      "src20_success": False,
      "message": "token not previously deployed, expect fail/fail - OK"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.2 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "1.1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, expect success/fail - UPDATE SRC20 Results"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.2 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": 1.1
    },
    "expectedOutcome": {
      "stamp_success": False,
      "src20_success": False,
      "message": "token not previously deployed, expect success/fail - OK "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.2 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "1.1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, expect success/fail - UPDATE SRC20 Results"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.2 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": 1.1
    },
    "expectedOutcome": {
      "stamp_success": False,
      "src20_success": False,
      "message": "token not previously deployed, expect fail/fail - OK"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.3 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed, expect success/success - OK "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.3 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": 1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed, expect success/success - OK "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.3 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed, expect success/success - OK"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.3 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": 1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed, expect success/success - OK"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.4 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "01"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed, current success/success - TBD"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.4 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "01"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "integer literals are not permitted in JSON- test modified from 01 to '01' - success/success - TBD"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.4 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "01"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token not previously deployed  current success/success - TBD "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.4 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "01"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "integer literals are not permitted in JSON- test modified from 01 to '01'  - current success/success - TBD "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "1 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, current success/fail - TBD"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": " 1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, current success/fail - TBD"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "1 "
    },
      "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, current success/fail - TBD"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": " 1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token not previously deployed, current success/fail - TBD"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.6 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": "1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.6 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": 1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.6 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": "1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success --- debug to give user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.6 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": 1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- debug to give user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.7 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": "1.00"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.7 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": 1.00
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, current FAIL/FAIL - UPDATE STAMP Result - could have historic stamp implications - will need activation block"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.7 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": "1.00"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- debug to give user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.7 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": 1.00
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- debug to give user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.8 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": "1.1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.8 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": 1.1234
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token previously deployed, current FAIL/FAIL - UPDATE STAMP Result? cannot mint fractions was was prior expectation"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.8 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": "1.1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- debug to give user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.8 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": 1.1234
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- debug to give user balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.9 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": "1.12340"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.9 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": 1.12340
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token previously deployed, current FAIL/FAIL - UPDATE STAMP Result - could have historic stamp implications - will need activation block"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.9 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": "1.12340"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success - user has simulated balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.9 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": 1.12340
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- user has simulated balance"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.10 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": "1.12345",
      "deci": "4"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token previously deployed, - UNKNOWN STATUS DEBUG SIM WITH DECIMAL VALUE HANDLING - TBD /FAIL ? "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token mint, scenario No.10 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "kevin",
      "amt": 1.12345,
      "deci": 4
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token previously deployed, - UNKOWN STATUS DEBUG SIM WITH DECIMAL VALUE HANDLING - TBD /FAIL ? "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.10 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": "1.12345",
      "deci": "4"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token previously deployed, - UNKNOWN STATUS DEBUG SIM WITH DECIMAL VALUE HANDLING - TBD /FAIL ? "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token operations, scenario No.10 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "kevin",
      "amt": 1.12345,
      "deci": "4"
    },
      "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
      "message": "token previously deployed, - UNKNOWN STATUS DEBUG SIM WITH DECIMAL VALUE HANDLING - TBD /FAIL ? "
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token operations, scenario No.11 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec0",
      "amt": "1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success, DEBUG SIM FOR 0 DEC"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token operations, scenario No.11 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec0",
      "amt": 1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token previously deployed, DEBUG SIM FOR 0 DEC"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.11 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec0",
      "amt": "1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success - DEBUG SIM FOR 0 DEC"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },
  {
    "description": "Test case for SRC-20 token transfer, scenario No.11 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec0",
      "amt": 1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": True,
      "message": "token  previously deployed, expect success/success -- DEBUG SIM FOR 0 DEC"
    },
    "source": "1SourceAddr",
    "destination": "1DestAddr",
    "btc_amount": 0.0,
    "fee": 0.0,
    "decoded_tx": "{}",
    "keyburn": 1,
    "tx_index": 0,
    "block_index": 0,
    "block_time": 0,
    "is_op_return": False,
    "valid_stamps_in_block": [],
    "valid_src20_in_block": [],
    "p2wsh_data": None,
    "tx_hash": "dummy_tx_hash"
  },



]