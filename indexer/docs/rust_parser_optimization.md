# Rust Parser Optimization Strategy

This document outlines potential optimizations for the Bitcoin Stamps indexer by leveraging the Rust parser more effectively, reducing redundant work done in Python when the Rust parser is enabled.

## Current Flow (with Rust Parser Enabled)

1.  **`filter_block_transactions`:**
    *   Receives all transaction hexes for a block.
    *   Separates known `stamp_issuance` transactions (identified via Counterparty API data). These are *always* included.
    *   Passes the hexes of *non-issuance* transactions to `backend_instance._parser.batch_parse_transactions`.
    *   The Rust parser deserializes/analyzes these transactions natively to filter based on SRC-20 criteria (P2WSH/Multisig patterns matching `quick_filter_src20_transaction` logic).
    *   Rust returns a list of transactions (e.g., their `txid`s or the original hex) that passed the filter.
    *   Python combines the known `stamp_issuance` transactions and the filtered non-issuance transactions into the `raw_transactions` dictionary.

2.  **`follow` loop:**
    *   Iterates through `raw_transactions` (containing both issuances and filtered non-issuances).
    *   Calls `process_tx` for each transaction.

3.  **`process_tx`:**
    *   Retrieves the `tx_hex`.
    *   Calls `list_tx`.

4.  **`list_tx`:**
    *   Calls `get_tx_info`.

5.  **`get_tx_info`:**
    *   **Redundancy:** Calls `backend_instance.deserialize(tx_hex)` again, even for transactions already filtered by Rust.
    *   Calls `process_vout` on the Python-deserialized object (`ctx`) to extract script details (`pubkeys_compiled`, `keyburn`, `is_op_return`, `is_olga`, `p2wsh_data_chunks`).
    *   If multisig, calls `decode_checkmultisig` for ARC4 decryption and data/destination extraction.
    *   Constructs and returns `TransactionInfo`.

6.  **`process_tx` (Continued):**
    *   Packages the data from `TransactionInfo` into a `TxResult`.

## Proposed Optimized Flow (with Rust Parser Enabled)

The goal is to have the Rust parser perform more of the initial analysis and return structured data, avoiding the redundant Python deserialization and processing for transactions it has already validated.

1.  **`filter_block_transactions`:**
    *   Identifies `stamp_issuance` transactions (same as before).
    *   Passes non-issuance transaction hexes to an enhanced Rust `batch_parse_and_extract` function.
    *   Rust performs filtering *and* extracts key data fields for the transactions that pass the filter. This could include:
        *   `data` (decoded/decrypted payload)
        *   `destination`, `destination_nvalue` (if applicable, from multisig/P2WSH)
        *   `keyburn`
        *   `is_op_return`
        *   `is_olga` (Could potentially also process issuance txns)
        *   `p2wsh_data_chunks` (Could potentially also process issuance txns)
        *   *(Maybe `source` - requires prev tx lookup, might be too complex)*
    *   Rust returns a list/map of `txid` -> `extracted_data_struct`.
    *   Python stores these structured results.

2.  **`follow` loop:**
    *   Iterates through transactions.
    *   Calls `process_tx`.

3.  **`process_tx`:**
    *   **If the transaction `txid` has pre-extracted Rust data:**
        *   Bypasses `list_tx` and `get_tx_info`.
        *   Directly uses the `extracted_data_struct` from Rust.
        *   Still needs to fetch `source` and `prev_tx_hash` by calling `backend_instance.getrawtransaction` for the *previous* transaction and deserializing *that* (this part seems unavoidable without major changes).
        *   Constructs `TxResult` using Rust data and the fetched source/prev_tx info.
    *   **If the transaction is a `stamp_issuance` or Rust processing failed (fallback):**
        *   Calls `list_tx` -> `get_tx_info` -> `process_vout` etc. as in the current flow.

## Benefits

*   Eliminates redundant deserialization of transactions in Python that Rust has already processed.
*   Reduces Python object creation overhead.
*   Leverages Rust's performance for script analysis (like `process_vout` logic) and potentially ARC4 decryption (`decode_checkmultisig`).

## Implementation Considerations & Impact Analysis

### Potential Implementation Stages (Lowest to Highest Risk)

1.  **Stage 1: Extract Simple Flags in Rust (Low Impact)**
    *   **Change:** Modify Rust `batch_parse_transactions` to also return simple boolean flags like `is_op_return` and `keyburn` for filtered non-issuance transactions.
    *   **Python:** Update `process_tx` to use these flags if available from Rust, skipping parts of `get_tx_info`/`process_vout`.
    *   **Risk/Validation:** Low. Requires comparing flag values between Rust and Python paths.

2.  **Stage 2: Extract Script Data in Rust (Medium Impact)**
    *   **Change:** Enhance Rust function to replicate `process_vout` logic (identify P2WSH/Multisig, extract `pubkeys_compiled`, `p2wsh_data_chunks`, `is_olga`) for filtered non-issuance transactions.
    *   **Python:** Update `process_tx` to use this structured data, bypassing `process_vout` when Rust data is present.
    *   **Risk/Validation:** Medium. Script parsing logic needs precise mirroring. Requires comparing extracted script details.

3.  **Stage 3: Extract Decrypted Data in Rust (High Impact)**
    *   **Change:** Implement ARC4 decryption (`decode_checkmultisig` logic) in Rust. Extract `data`, `destination`, `destination_nvalue`.
    *   **Python:** Update `process_tx` to use this data, bypassing `decode_checkmultisig`.
    *   **Risk/Validation:** High. Cryptographic logic must be identical. Requires rigorous comparison of final extracted data.

### Handling `stamp_issuance` Transactions

*   **Identification:** Stamp issuances are identified *before* filtering, using data from the Counterparty API. They are *always* included in `raw_transactions` and bypass the Rust/Python filtering applied to non-issuance transactions.
*   **Current Processing:** Even though `source`/`destination` often come from the API data for issuances, the Python function `process_vout` is still called on the deserialized issuance transaction. This is primarily used to detect the OLGA P2WSH format (`is_olga = True`) and extract the specific `p2wsh_data_chunks` used for CP-encoded OLGA stamps.
*   **Impact of Optimization:** The core optimization affects non-issuance transactions filtered by Rust. It doesn't inherently break issuance processing.
*   **Recommendation:** Initially, keep the Python path (`list_tx` -> `get_tx_info` -> `process_vout`) fully intact for `stamp_issuance` transactions. Focus Rust optimizations (Stages 1-3) only on the *non-issuance* transactions identified by the initial Rust filter. Optimizing `process_vout` for issuances within Rust can be a separate, later consideration if needed.

### Validation Strategy

After implementing each stage, rigorous validation is required:

*   Run the indexer over a significant block range *with* the Rust optimization enabled.
*   Run the indexer over the *same* block range *without* the Rust optimization (forcing the Python fallback).
*   Compare the resulting databases (specifically `stamps`, `balances`, `asset_owners`, `src20_transactions`, `src101_transactions`, etc.) for *exact* matches. Any discrepancy indicates a logic mismatch between the Rust path and the Python path.

### Pre-Implementation Testing Requirements

Before starting the implementation of the phased optimizations, it is crucial to enhance the existing test suite (`@tests`) to provide a safety net and validate logic parity between the Python and future Rust paths. Additions/enhancements should include:

1.  **Detailed Data Extraction Comparison:**
    *   **Goal:** Compare the individual data fields extracted by the current Python path (`get_tx_info` -> `process_vout` -> `decode_checkmultisig`) against the data structure the *enhanced* Rust parser *will* produce.
    *   **Implementation:** Enhance `tests/test_parser_comparison.py` or create a new `tests/test_rust_extraction_parity.py`.
    *   **Methodology:**
        *   Use diverse input transaction hexes (SRC-20 Multisig, P2WSH, OP_RETURN, invalid formats, standard BTC, stamp issuances).
        *   Get baseline results using the current Python `get_tx_info` path.
        *   Define the *expected* structured output from the *future* Rust parser for each stage (initially, this might be manually defined based on Python's output).
        *   Assert field-by-field equality (e.g., `expected_rust_output.keyburn == python_output.keyburn`). As Rust is enhanced, compare Python path vs. actual Rust path output directly.

2.  **Block-Level Processing Parity (Mixed Types):**
    *   **Goal:** Ensure processing a full block with mixed transaction types yields identical `TxResult` objects regardless of whether the Rust optimization or Python fallback is used.
    *   **Implementation:** Add test cases to `tests/test_block_tx.py` or `tests/test_integration_block_processing.py`.
    *   **Methodology:**
        *   Construct test blocks with mixes of: stamp issuances, valid SRC-20 (Multisig & P2WSH), invalid SRC-20 attempts, standard BTC txs.
        *   Run block processing forcing the Python path and again with the (future/simulated) Rust optimization path.
        *   Compare the final list of `TxResult` objects, asserting identical content and order.

3.  **Stamp Issuance Integrity:**
    *   **Goal:** Explicitly verify that `stamp_issuance` processing (especially `is_olga`, `p2wsh_data_chunks` extraction via `process_vout`) remains unchanged by optimizations applied to *non-issuance* transactions.
    *   **Implementation:** Add specific test cases to `tests/test_transactions.py` or `tests/test_block_tx.py` focusing *only* on stamp issuances (standard and OLGA).
    *   **Methodology:** Assert that the relevant fields in the `TxResult` are correct and consistent, regardless of the optimization path taken for other transaction types in the block.

**Integration:** Ensure any new test files are added to `indexer/tools/run_checks.py` for inclusion in the standard test runs. 