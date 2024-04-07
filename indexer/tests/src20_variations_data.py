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
      "tick": "TEST"
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
    "description": "Test case for SRC-20 token deployment, scenario No.2 (Variant 1)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.2 (Variant 2)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.3 (Variant 1)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.3 (Variant 2)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.4 (Variant 1)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.4 (Variant 2)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 1)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 2)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 3)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.5 (Variant 4)",
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
    "description": "Test case for SRC-20 token deployment, scenario No.6 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "01"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.6 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "01"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.8 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "1 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.8 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": " 1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.8 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "1 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.8 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": " 1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.9 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.9 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.9 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.9 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.10 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.10 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.11",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.12",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.13 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.13 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.14",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.15",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.16 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.16 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.17",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.18",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.19 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token transfer, scenario No.19 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token mint, scenario No.20",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token operations, scenario No.21",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
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
    "description": "Test case for SRC-20 token operations, scenario No.22 (Variant 1)",
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
    "description": "Test case for SRC-20 token operations, scenario No.22 (Variant 2)",
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
    "description": "Test case for SRC-20 token transfer, scenario No.22 (Variant 3)",
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
    "description": "Test case for SRC-20 token transfer, scenario No.22 (Variant 4)",
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
  {
    "description": "Test case for SRC-20 token mint, scenario No.23 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec0",
      "amt": "1.0"
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
    "description": "Test case for SRC-20 token transfer, scenario No.23 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec0",
      "amt": "1.0"
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
    "description": "Test case for SRC-20 token mint, scenario No.24",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec0",
      "amt": 1.0
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
    "description": "Test case for SRC-20 token transfer, scenario No.25",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec0",
      "amt": 1.0
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
    "description": "Test case for SRC-20 token mint, scenario No.26 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec0",
      "amt": "1.1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
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
    "description": "Test case for SRC-20 token transfer, scenario No.26 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec0",
      "amt": "1.1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
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
    "description": "Test case for SRC-20 token mint, scenario No.27",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec0",
      "amt": 1.1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
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
    "description": "Test case for SRC-20 token transfer, scenario No.28",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec0",
      "amt": 1.1
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": False,
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
    "description": "Test case for SRC-20 token mint, scenario No.29 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": ".1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.29 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": ".1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.30",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": .1234
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.31",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": .1234
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.32 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": "01.1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.32 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": "01.1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.33",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": 01.1234
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.34",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": 01.1234
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.35 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": "1 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.35 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": " 1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.35 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": "1.1234 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.35 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": " 1.1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.35 (Variant 5)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": "1 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.35 (Variant 6)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": " 1"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.35 (Variant 7)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": "1.1234 "
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.35 (Variant 8)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": " 1.1234"
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.36 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": "1."
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.36 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "max": "1",
      "lim": 1.
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.36 (Variant 3)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": "1."
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token deployment, scenario No.36 (Variant 4)",
    "src20JsonString": {
      "p": "src-20",
      "op": "deploy",
      "tick": "test",
      "lim": "1",
      "max": 1.
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.37 (Variant 1)",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": "1."
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.37 (Variant 2)",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": "1."
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token mint, scenario No.38",
    "src20JsonString": {
      "p": "src-20",
      "op": "mint",
      "tick": "dec4",
      "amt": 1.
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
    "description": "Test case for SRC-20 token transfer, scenario No.39",
    "src20JsonString": {
      "p": "src-20",
      "op": "transfer",
      "tick": "dec4",
      "amt": 1.
    },
    "expectedOutcome": {
      "stamp_success": True,
      "src20_success": "",
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
  }
]