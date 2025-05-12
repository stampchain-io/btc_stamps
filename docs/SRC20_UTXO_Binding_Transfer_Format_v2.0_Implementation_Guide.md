# SRC-20 UTXO Binding & Transfer Format v2.0 Implementation Guide

This document provides a step-by-step integration plan to support the new SRC-20 UTXO Binding & Transfer Format v2.0 in the Bitcoin Stamps Indexer.

---
## Table of Contents
1. [Overview](#overview)
2. [Proposal Summary](#proposal-summary)
3. [Data Format Specification](#data-format-specification)
4. [Utility Functions](#utility-functions)
5. [Parser Integration](#parser-integration)
6. [SRC-20 Module Integration](#src-20-module-integration)
7. [Block Processing Integration](#block-processing-integration)
8. [Balance Updates & Ledger Validation](#balance-updates--ledger-validation)
9. [Testing Strategy](#testing-strategy)
10. [Backward Compatibility & Migration](#backward-compatibility--migration)
11. [Next Steps & Enhancements](#next-steps--enhancements)

---
## 1. Overview
The SRC-20 UTXO Binding & Transfer Format v2.0 proposal ([Issue #484](https://github.com/stampchain-io/btc_stamps/issues/484)) introduces a compact binary transfer format enabling:
- Reduced on-chain size (≈60 bytes vs JSON)
- Native UTXO binding for atomic swaps
- Simplified parsing and lower fees

This guide outlines all code changes required in the indexer to fully support this format.

---
## 2. Proposal Summary
- **Prefix**: 6 bytes `0x73 74 61 6d 70 3a` (`"stamp:"`)
- **Version**: 1 byte (current `0x01`)
- **Protocol Operation**: 1 byte (`0x12` = transfer)
- **Tick**: 20 bytes UTF-8, left-aligned, zero-padded
- **Amount**: 8 bytes uint64 BE
- **Decimals**: 8 bytes uint64 BE

Operations occur via:
- UTXO attach: OP_RETURN or P2WSH output carrying the binary blob
- PSBT atomic swaps: mixed BTC+token inputs/outputs

---
## 3. Data Format Specification
| Bytes    | Field         | Length | Details                                          |
|----------|---------------|--------|--------------------------------------------------|
| 0–5      | Fixed Prefix  | 6      | `b"stamp:"`                                     |
| 6        | Version       | 1      | `0x01`                                           |
| 7        | Protocol Op   | 1      | `0x12` = SRC-20 transfer                         |
| 8–27     | Tick          | 20     | UTF-8 name, left-aligned, pad `0x00`             |
| 28–35    | Amount        | 8      | `uint64` big-endian                               |
| 36–43    | Decimals      | 8      | `uint64` big-endian; number of decimal places     |

---
## 4. Utility Functions
Create helper functions in `indexer/src/index_core/util.py`:

```python
# In index_core/util.py
PREFIX = b"stamp:"

def encode_transfer_data(tick: str, amount: int, decimals: int,
                         version: int = 1, protocol_op: int = 0x12) -> bytes:
    """Pack fields into the v2 binary transfer format."""
    b = bytearray()
    b += PREFIX
    b += version.to_bytes(1, "big")
    b += protocol_op.to_bytes(1, "big")
    tick_bytes = tick.encode("utf-8")[:20]
    b += tick_bytes.ljust(20, b"\x00")
    b += amount.to_bytes(8, "big")
    b += decimals.to_bytes(8, "big")
    return bytes(b)


def decode_transfer_data(blob: bytes) -> dict:
    """Unpack the binary transfer payload into its fields."""
    assert blob.startswith(PREFIX), "Invalid SRC-20 prefix"
    version = blob[6]
    protocol_op = blob[7]
    tick = blob[8:28].rstrip(b"\x00").decode("utf-8")
    amount = int.from_bytes(blob[28:36], "big")
    decimals = int.from_bytes(blob[36:44], "big")
    return {"version": version, "op": protocol_op,
            "tick": tick, "amt": amount, "dec": decimals}
```

---
## 5. Parser Integration
**File**: `indexer/src/index_core/parser.py`

1. **Detect new format** in `quick_filter_src20_transaction(ctx)`:
   - After collecting `p2wsh_data_chunks`, reassemble and check for `config.PREFIX`.
   - Call `decode_transfer_data(blob)` when prefix found.
2. **OP_RETURN Support**: in `get_tx_info`, detect OP_RETURN outputs:
   - If `data` (from OP_RETURN) starts with `PREFIX`, replace JSON parse logic with `decode_transfer_data(data)`.
3. **Propagate payload**:
   - Attach parsed dict to `EnhancedCTransaction` via `ctx._extra_attrs['src20_payload']`.
   - Ensure downstream code sees `payload = ctx.src20_payload`.

_Pseudocode Snippet:_
```python
# inside quick_filter_src20_transaction:
if combined_data.startswith(config.PREFIX):
    parsed = decode_transfer_data(combined_data)
    ctx._extra_attrs['src20_payload'] = parsed
    return True
```

---
## 6. SRC-20 Module Integration
**File**: `indexer/src/index_core/src20.py`

1. **Extend `parse_src20`**:
   - Detect binary payload: if `src20_dict` is None and `payload` in context, branch to binary handler.
2. **Create `parse_v2_transfer`**:
   - Accept raw fields (`version`, `op`, `tick`, `amt`, `dec`) and normalize.
   - Populate a `src20_dict` compatible with `Src20Processor`:
     ```python
     src20 = {
       'p': 'src-20', 'op': 'TRANSFER', 'tick': payload['tick'],
       'amt': Decimal(payload['amt']), 'dec': payload['dec'],
       'creator': source, 'destination': destination, ...
     }
     ```
3. **Integrate in `parse`**:
   - Before JSON handling, check for `src20_payload` and call `parse_v2_transfer`.

---
## 7. Block Processing Integration
**File**: `indexer/src/index_core/blocks.py`

1. **`filter_block_transactions`**:
   - Ensure P2WSH & OP_RETURN binary-format txs pass through as `raw_transactions`.
2. **`BlockProcessor.process_transaction_results`**:
   - After `parse_stamp`, inspect `ctx.src20_payload` and feed into `parse_src20`.
3. **`BlockProcessor.finalize_block`**:
   - Confirm new v2 transfers appear in `processed_src20_in_block`.
   - Ledger hashing (`create_check_hashes` / `validate_src20_ledger_hash`) must account for UTXO-binding events and multi-token swaps.

---
## 8. Balance Updates & Ledger Validation
- **`update_src20_balances`**: verify debit/credit logic works unchanged for v2 transfers.
- **PSBT Atomic Swaps**: new tests to simulate dual-input PSBTs producing balanced debits/credits.
- **Multi-Token Transfers**: ensure `process_balance_updates` handles multiple payloads in one tx.

---
## 9. Testing Strategy
- **Unit Tests**:
  - `encode_transfer_data` / `decode_transfer_data` round-trip.
  - Parser detection of v2 format in both P2WSH and OP_RETURN.
  - `parse_v2_transfer` correctness.
- **Integration Tests**:
  - Simulated block with v2 transfers, run `filter_block_transactions -> parse -> finalize_block`.
  - Assert balances and ledger hash correctness via `validate_src20_ledger_hash`.

---
## 10. Backward Compatibility & Migration
- Existing JSON-based SRC-20 parsing remains unchanged for blocks < `BTC_SRC20_UTXO_BINDING_BLOCK`.
- Introduce configuration flag or use `version` field to smoothly support both formats.

---
## 11. Next Steps & Enhancements
- Support future `protocol_op` codes beyond transfers (e.g., atomic swap flags).
- Optimize bulk transfers with batched multi-payload decoding.
- Explore on-chain indexing improvements for binding metadata.

---
*Document generated to guide developers through implementing Issue #484 in the Bitcoin Stamps Indexer.* 