# Thread Safety Testing for SRC-20 Processor

## Overview

The SRC-20 processor in the Bitcoin Stamps indexer needs to be thread-safe to handle concurrent transaction processing correctly. This document outlines the thread safety requirements, testing approaches, and current test implementations.

## Thread Safety Requirements

The SRC-20 processor uses the following mechanisms to ensure thread safety:

1. **Thread Locks**: A lock is passed to the `parse_src20` function to protect access to shared resources, particularly the `processed_src20_in_block` list.

2. **Protected Shared State**: The lock protects critical sections of code that modify shared resources, ensuring atomic operations.

3. **Transaction Copying**: Transactions are copied before modification to avoid race conditions from concurrent modifications.

4. **Cache Protection**: The cache manager uses thread-safe mechanisms for updating cached values.

## Test Implementations

We have two implementations for testing thread safety:

### 1. Standalone Test Script

**Location**: `indexer/tests/thread_safety/test_thread_safety.py`

**Purpose**: This standalone script provides:
- A minimal implementation test that verifies basic lock behavior
- A race condition demonstration using counter patterns to show what happens without locks
- Simple test execution without dependencies on test frameworks

**How to run**:
```bash
cd indexer
poetry run python tests/thread_safety/test_thread_safety.py
```

**Test results**: 
- The lock mechanism test passes successfully
- The race condition demonstration clearly shows issues when locks are not used

### 2. Pytest Tests

**Location**: `indexer/tests/test_src20_thread_safety.py`

**Purpose**: These tests provide comprehensive verification of thread safety mechanisms:
- Basic thread safety with concurrent transaction processing
- Handling of duplicate ticks with concurrent access
- Demonstration of race conditions without locks
- Parameterized tests with varying concurrency levels

**How to run**:
```bash
cd indexer
poetry run pytest tests/test_src20_thread_safety.py -v
```

You can also run using the taskipy task:
```bash
cd indexer
poetry run task test-thread-safety
```

**Test results**:
- All thread safety tests pass successfully
- The importance of locks is clearly demonstrated through the counter test

## Understanding the Thread Safety Mechanisms

### Lock-Protected Operations

The most critical part of the thread safety implementation is the proper use of locks when modifying shared resources. In the SRC-20 processor:

```python
# Access to shared resources is protected with locks
with lock:
    # Check for duplicates
    if tick in processed_ticks_set:
        return False
        
    # Add to the processed list
    processed_list.append(tx_copy)
    processed_ticks_set.add(tick)
```

Without this lock protection, the following race conditions could occur:

1. Two threads check for duplicates simultaneously and both see that a tick isn't present
2. Both threads add the same tick, resulting in duplicates
3. One thread could read a partially modified state from another thread

### Race Condition Demonstration

The counter test in both test implementations clearly demonstrates what happens without proper locking:

```python
# Without a lock:
counter = 0
# Thread 1 reads counter as 0
# Thread 2 reads counter as 0
# Thread 1 increments to 1
# Thread 2 increments to 1 (should be 2)
# Lost update!

# With a lock:
counter = 0
with lock:  # Thread 2 waits here until Thread 1 finishes
    # Thread 1 reads counter as 0
    # Thread 1 increments to 1
# Thread 2 now gets the lock
with lock:
    # Thread 2 reads counter as 1
    # Thread 2 increments to 2
# No lost updates!
```

## Maintaining Thread Safety

When modifying the SRC-20 processor code, keep these guidelines in mind:

1. Always use the provided lock when accessing or modifying the shared `processed_src20_in_block` list
2. Ensure that checks and modifications to shared state are done atomically within the same lock
3. Don't introduce new shared mutable state without proper lock protection
4. When in doubt, use the thread safety tests to verify your changes

## Future Improvements

Potential improvements to thread safety testing include:

1. **Stress Testing**: Add tests with higher concurrency and more transactions to stress test the lock mechanisms
2. **Actual Implementation Testing**: Create a more comprehensive mock implementation for testing the real SRC-20 processor
3. **Performance Testing**: Measure the impact of locking on performance and optimize if needed
4. **Visualization**: Add tools to visualize race conditions for educational purposes

## Summary

Thread safety is critical for the correct functioning of the SRC-20 processor. The test implementations verify that the current locking mechanisms effectively prevent race conditions and ensure proper transaction processing, even under concurrent access. 