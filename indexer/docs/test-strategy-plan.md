# Test Strategy Plan for Bitcoin Stamps Indexer

## 1. Overview

This document outlines a comprehensive test strategy for the Bitcoin Stamps Indexer. Our focus is to ensure that any optimizations—especially with the new Rust parser enhancements—do not alter the expected indexer logic. The strategy covers validating balance calculations, comparing parser outputs (Python vs. Rust), and verifying end-to-end block processing. We will also leverage both live database connections and offline data fixtures in our testing.

## 2. Areas of Enhanced Test Coverage

### A. Balance Calculations
- Develop unit tests for critical functions in blocks.py (e.g., finalize_block, commit_and_update_block, balance update routines).
- Simulate transactions with known outcomes and validate that ledger hashes and balance tables are updated correctly. In particular on and after consensus changing blocks outlined in config (e.g., CP_SRC20_GENESIS_BLOCK, BTC_SRC20_GENESIS_BLOCK, etc.).
- **Recent Progress:** Implemented unit tests for SRC-20 balance normalization and update operations, as seen in `tests/test_src20_balance.py` and `tests/test_src20_update_valid.py`.

### B. Rust Parsing Impact
- Create tests that feed identical blockchain transaction data to both Python and Rust parser implementations and compare outputs.
- Design edge-case tests that push the boundaries of the Rust parser (high load, non-standard transaction formats) to ensure consistency.

### C. End-to-End Block Processing
- Extend integration tests to simulate complete block processing, including rollback scenarios and chain reorganizations.
- Compare outputs against a trusted "golden" dataset. Use this dataset as a local fixture to replicate realistic blockchain data scenarios.

## 3. Testing Infrastructure Enhancements

- **Live Database Tests:** Continue to utilize dedicated test databases (or isolated instances) that mirror production and development environments for integration tests.
- **Offline Testing:** Store snapshots of compliant blockchain data (in JSON or similar format) as fixtures. Use these in CI pipelines to simulate block processing and balance verification in an offline mode.
- **Hybrid Approach:** Combine offline tests (fast, reliable, good for regression) with periodic live tests to ensure real-world alignment.
- **Tooling:** Leverage test runners like pytest for parametrization, improved reporting, and integration with continuous integration systems.

## 4. Implementation Steps

1. **Unit Testing:** Start by writing unit tests for functions in blocks.py and related modules that involve balance calculation and ledger hash validation.
2. **Parser Comparison Tests:** Develop test cases that run transaction data through both the Python and Rust parser paths and assert identical outputs.
3. **Integration Testing:** Design end-to-end tests that simulate full block processing using both live DB connections and offline fixtures. Include scenarios for normal processing, rollbacks, and chain reorganizations.
4. **Fixture Management:** Create and maintain a set of golden data sets that represent various blockchain states. These can be used for offline testing in CI.
5. **Continuous Validation:** Integrate these tests into the CI/CD pipeline to continually validate performance and correctness after each change.

## 5. Conclusion

This test strategy provides a robust framework to ensure that optimizations—especially those related to the Rust parser—do not compromise the core functionality of the Bitcoin Stamps Indexer. By combining unit tests, parser comparison tests, and integration tests using both live and offline data, we can confidently advance enhancements while maintaining system integrity.

## 6. Recent Test Implementations and Future Directions

- **Recent Progress:**
  - Unit tests for SRC-20 normalization and balance updates have been successfully implemented in `tests/test_src20_balance.py` and `tests/test_src20_update_valid.py`.
  - These tests validate that valid values are correctly processed and that numbers exceeding allowed precision raise appropriate errors.
  - All implemented tests have passed, confirming the reliability of SRC-20 balance calculation functions.

- **Next Steps:**
  - Expand test coverage by adding integration tests that simulate complete block processing and ledger hash validations.
  - Develop test cases to compare outputs of the Python and Rust parsers to ensure consistency across protocol optimizations.
  - Enhance caching and database interaction tests to verify accurate balance updates under various transaction scenarios.
