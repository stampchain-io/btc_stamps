# Performance History

A short record of validated performance results, kept after retiring the longer
`performance-improvement-{plan,results,summary}.md` proposal drafts (most of which described
a protocol-data-extraction redesign that was never built).

## Rust transaction filtering (validated)

The Rust parser filters transactions in Rust — `process_transaction_chunk` only returns
transactions whose `should_include` flag is true, so Python receives just the relevant
subset. Benchmarking across blocks 795419–795423 measured an overall **~2.53x speedup**
versus an equivalent Python-only filtering path. This optimization is implemented and
remains current; see [`indexer/src/rust_parser/README.md`](../src/rust_parser/README.md).
