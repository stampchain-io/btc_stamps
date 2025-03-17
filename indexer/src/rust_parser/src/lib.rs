#![allow(non_local_definitions)]

mod arc4;
mod constants;

use bitcoin::blockdata::transaction::{Transaction, TxIn, TxOut};
use bitcoin::consensus::Decodable;
use bitcoin::Block;
use log::{debug, error};
use pyo3::prelude::*;
use rayon::prelude::*;
use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;

use crate::arc4::{arc4_decrypt_chunk, init_arc4};
use crate::constants::{BURNKEYS, PREFIX};

// Add a simple LRU cache implementation
struct LruCache<K, V> {
    map: HashMap<K, V>,
    queue: VecDeque<K>,
    capacity: usize,
    memory_limit: usize,
    current_memory: usize,
}

impl<K, V> LruCache<K, V>
where
    K: Clone + std::hash::Hash + Eq + std::fmt::Debug + ToString,
    V: Clone,
{
    fn new(capacity: usize, memory_limit: usize) -> Self {
        LruCache {
            map: HashMap::with_capacity(capacity),
            queue: VecDeque::with_capacity(capacity),
            capacity,
            memory_limit,
            current_memory: 0,
        }
    }

    fn get(&mut self, key: &K) -> Option<V> {
        if let Some(value) = self.map.get(key) {
            // Move key to the end of the queue (most recently used)
            if let Some(pos) = self.queue.iter().position(|k| k == key) {
                let k = self.queue.remove(pos).unwrap();
                self.queue.push_back(k);
            }
            Some(value.clone())
        } else {
            None
        }
    }

    fn insert(&mut self, key: K, value: V, key_size: usize, value_size: usize) {
        let entry_size = key_size + value_size;

        // If key already exists, update it and move to end of queue
        if let std::collections::hash_map::Entry::Occupied(mut e) = self.map.entry(key.clone()) {
            if let Some(pos) = self.queue.iter().position(|k| k == &key) {
                let old_key = self.queue.remove(pos).unwrap();
                self.queue.push_back(old_key);
            }
            // Update the value
            e.insert(value);
            return;
        }

        // Check if we need to make room (either by count or memory)
        while (!self.queue.is_empty())
            && (self.queue.len() >= self.capacity
                || self.current_memory + entry_size > self.memory_limit)
        {
            if let Some(old_key) = self.queue.pop_front() {
                if let Some(old_value) = self.map.remove(&old_key) {
                    // Estimate memory freed (this is an approximation)
                    let old_key_size = std::mem::size_of_val(&old_key)
                        + old_key.to_string().len() * std::mem::size_of::<u8>();
                    let old_value_size = std::mem::size_of_val(&old_value);
                    self.current_memory = self
                        .current_memory
                        .saturating_sub(old_key_size + old_value_size);
                }
            }
        }

        // Insert new entry
        self.map.insert(key.clone(), value);
        self.queue.push_back(key);
        self.current_memory += entry_size;
    }

    fn len(&self) -> usize {
        self.map.len()
    }

    fn memory_usage(&self) -> usize {
        self.current_memory
    }

    fn clear(&mut self) {
        self.map.clear();
        self.queue.clear();
        self.current_memory = 0;
    }

    fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
        self.map.iter()
    }
}

#[pyclass]
pub struct FastTransactionParser {
    tx_cache: Mutex<LruCache<String, Vec<u8>>>,
    max_cache_size: usize,
    max_memory_bytes: usize,
}

#[pymethods]
impl FastTransactionParser {
    #[new]
    #[pyo3(signature = (use_cache = true))]
    fn new(use_cache: bool) -> Self {
        let cache_size = if use_cache { 10000 } else { 0 };
        let memory_limit = if use_cache { 100 * 1024 * 1024 } else { 0 }; // 100MB if cache enabled, 0 if disabled

        FastTransactionParser {
            tx_cache: Mutex::new(LruCache::new(cache_size, memory_limit)), // 10K entries, 100MB or disabled
            max_cache_size: cache_size,
            max_memory_bytes: memory_limit,
        }
    }

    fn deserialize_transaction(&self, tx_hex: &str) -> PyResult<TransactionInfo> {
        // Log the length of the transaction hex string
        log::debug!(
            "Deserializing transaction with hex length: {}",
            tx_hex.len()
        );

        // Check cache first if cache is enabled (max_cache_size > 0)
        if self.max_cache_size > 0 {
            if let Ok(mut cache) = self.tx_cache.lock() {
                if let Some(cached_tx) = cache.get(&tx_hex.to_string()) {
                    log::debug!("Cache hit for transaction");
                    if let Ok(tx) = Transaction::consensus_decode(&mut &cached_tx[..]) {
                        let txid = tx.txid().to_string();
                        return Ok(TransactionInfo::from_transaction(&tx, &txid));
                    }
                }
            }
        }

        // Parse hex and cache result
        let tx_bytes = hex::decode(tx_hex).map_err(|e| {
            error!("Failed to decode hex: {}", e);
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
        })?;

        // Log the length of the decoded transaction bytes
        log::debug!("Decoded transaction bytes length: {}", tx_bytes.len());

        let tx = Transaction::consensus_decode(&mut &tx_bytes[..]).map_err(|e| {
            error!("Failed to decode transaction: {}", e);
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid transaction: {}", e))
        })?;

        // Cache the raw bytes using the LRU cache if cache is enabled
        if self.max_cache_size > 0 {
            if let Ok(mut cache) = self.tx_cache.lock() {
                cache.insert(
                    tx_hex.to_string(),
                    tx_bytes.clone(),
                    tx_hex.len(),
                    tx_bytes.len(),
                );
            }
        }

        let txid = tx.txid().to_string();
        Ok(TransactionInfo::from_transaction(&tx, &txid))
    }

    #[allow(clippy::type_complexity)]
    fn parse_block(
        &self,
        block_hex: &str,
    ) -> PyResult<(
        Vec<String>,
        HashMap<String, String>,
        u32,
        String,
        Option<f64>,
    )> {
        let block_bytes = hex::decode(block_hex).map_err(|e| {
            error!("Failed to decode block hex: {}", e);
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
        })?;

        let block = Block::consensus_decode(&mut &block_bytes[..]).map_err(|e| {
            error!("Failed to decode block: {}", e);
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid block: {}", e))
        })?;

        // Create tx_hash_list with ALL transactions in original order for hash calculation
        let tx_hash_list: Vec<String> = block
            .txdata
            .iter()
            .map(|tx| tx.txid().to_string())
            .collect();

        log::debug!(
            "Processing {} transactions for block hash calculation",
            tx_hash_list.len()
        );

        // Create raw_transactions map with ALL transactions
        let mut raw_transactions: HashMap<String, String> = HashMap::new();
        for tx in &block.txdata {
            let tx_id = tx.txid().to_string();
            let tx_hex = hex::encode(bitcoin::consensus::serialize(tx));
            raw_transactions.insert(tx_id, tx_hex);
        }

        log::debug!(
            "Completed block processing with {} transactions",
            raw_transactions.len()
        );

        // Return a tuple directly instead of BlockInfo
        Ok((
            tx_hash_list,
            raw_transactions,
            block.header.time,
            block.header.prev_blockhash.to_string(),
            None, // bits as Option<f64>
        ))
    }

    pub fn batch_parse_transactions(&self, tx_hexes: Vec<&str>) -> PyResult<Vec<TransactionInfo>> {
        let start_time = std::time::Instant::now();
        let total_txs = tx_hexes.len();

        log::info!("Starting batch processing of {} transactions", total_txs);

        // For very large batches, process in chunks to avoid memory issues
        const CHUNK_SIZE: usize = 1000;
        let mut results = Vec::new();
        let mut total_processed = 0;
        let mut total_included = 0;

        // Process in chunks if the batch is large
        if total_txs > CHUNK_SIZE {
            log::info!(
                "Processing large batch in {} chunks",
                total_txs.div_ceil(CHUNK_SIZE),
            );

            for (chunk_idx, chunk) in tx_hexes.chunks(CHUNK_SIZE).enumerate() {
                log::debug!(
                    "Processing chunk {}/{} with {} transactions",
                    chunk_idx + 1,
                    total_txs.div_ceil(CHUNK_SIZE),
                    chunk.len()
                );

                let chunk_vec: Vec<String> = chunk.iter().map(|&s| s.to_string()).collect();
                let chunk_results = self.process_transaction_chunk(chunk_vec)?;
                total_processed += chunk.len(); // Count all transactions processed

                // Count transactions that should be included before filtering
                let should_include_count = chunk_results.len(); // This should already be filtered
                total_included += should_include_count;

                // Add all results from process_transaction_chunk (which should already be filtered)
                results.extend(chunk_results);

                log::debug!(
                    "Chunk {}: processed {} transactions, {} should be included ({}%)",
                    chunk_idx + 1,
                    chunk.len(),
                    should_include_count,
                    if !chunk.is_empty() {
                        should_include_count * 100 / chunk.len()
                    } else {
                        0
                    }
                );

                // Perform cache management after each chunk
                if let Ok(mut cache) = self.tx_cache.lock() {
                    let current_memory: usize = cache.memory_usage();

                    if current_memory >= self.max_memory_bytes {
                        log::info!(
                            "Cache limits reached during batch processing (memory: {:.2}MB/{:.2}MB), clearing cache",
                            current_memory as f64 / 1024.0 / 1024.0,
                            self.max_memory_bytes as f64 / 1024.0 / 1024.0
                        );
                        cache.clear();
                    }
                }
            }
        } else {
            // For smaller batches, process all at once
            let tx_hexes_vec: Vec<String> = tx_hexes.iter().map(|&s| s.to_string()).collect();
            let all_results = self.process_transaction_chunk(tx_hexes_vec)?;
            total_processed = tx_hexes.len(); // Count all transactions processed

            // Count transactions that should be included before filtering
            let should_include_count = all_results.len(); // This should already be filtered
            total_included += should_include_count;

            // Add all results from process_transaction_chunk (which should already be filtered)
            results.extend(all_results);

            log::debug!(
                "Small batch: processed {} transactions, {} should be included ({}%)",
                total_txs,
                should_include_count,
                if total_txs > 0 {
                    should_include_count * 100 / total_txs
                } else {
                    0
                }
            );
        }

        // Count how many transactions should be included
        let included_count = results.len();
        let duration = start_time.elapsed();

        log::info!(
            "Batch processing complete: {} transactions processed, {} included ({}%), took {:?}",
            total_txs,
            included_count,
            if total_txs > 0 {
                included_count * 100 / total_txs
            } else {
                0
            },
            duration
        );

        // Additional logging to help diagnose filtering issues
        log::info!(
            "Filtering summary: {} transactions processed by Rust, {} passed should_include check ({}%)",
            total_processed,
            total_included,
            if total_processed > 0 { total_included * 100 / total_processed } else { 0 }
        );

        // Return only transactions that should be included
        Ok(results)
    }

    // Helper method to process a chunk of transactions
    fn process_transaction_chunk(&self, tx_hexes: Vec<String>) -> PyResult<Vec<TransactionInfo>> {
        // Log the number of transactions being processed
        log::info!("Processing chunk of {} transactions", tx_hexes.len());

        // Create a vector to store the results
        let mut results = Vec::with_capacity(tx_hexes.len());
        let mut should_include_count = 0;
        let mut has_valid_pattern_count = 0;
        let mut has_valid_data_count = 0;
        let mut has_keyburn_count = 0;

        // Process each transaction in parallel
        let parsed_results: Vec<Option<TransactionInfo>> = tx_hexes
            .par_iter()
            .map(|tx_hex| {
                match hex::decode(tx_hex) {
                    Ok(tx_bytes) => {
                        match Transaction::consensus_decode(&mut &tx_bytes[..]) {
                            Ok(tx) => {
                                let txid = tx.txid().to_string();
                                log::debug!("Processing transaction {}", txid);

                                // Create TransactionInfo from the transaction
                                let tx_info = TransactionInfo::from_transaction(&tx, &txid);

                                // Log detailed information about the transaction
                                log::debug!(
                                    "Transaction {}: has_valid_pattern={}, has_valid_data={}, keyburn={}, should_include={}",
                                    txid, tx_info.has_valid_pattern, tx_info.has_valid_data, tx_info.keyburn, tx_info.should_include
                                );

                                // Return the TransactionInfo regardless of should_include
                                Some(tx_info)
                            },
                            Err(e) => {
                                error!("Failed to decode transaction in batch: {}", e);
                                None
                            }
                        }
                    },
                    Err(e) => {
                        error!("Failed to decode hex in batch: {}", e);
                        None
                    }
                }
            })
            .collect();

        // Iterate through the parsed results and filter out None values
        for tx_info in parsed_results.iter().flatten() {
            // Store the values we need for logging
            let txid = tx_info.txid.clone();
            let has_valid_pattern = tx_info.has_valid_pattern;
            let has_valid_data = tx_info.has_valid_data;
            let keyburn = tx_info.keyburn;
            let should_include = tx_info.should_include;

            // Update counters for logging
            if has_valid_pattern {
                has_valid_pattern_count += 1;
            }
            if has_valid_data {
                has_valid_data_count += 1;
            }
            if keyburn > 0 {
                has_keyburn_count += 1;
            }
            if should_include {
                should_include_count += 1;
            }

            // Add to results if should_include is true
            if should_include {
                results.push(tx_info.clone());
                log::debug!("Including transaction {}", txid);
            } else {
                log::debug!(
                    "Excluding transaction {}: has_valid_pattern={}, has_valid_data={}, keyburn={}",
                    txid,
                    has_valid_pattern,
                    has_valid_data,
                    keyburn
                );
            }
        }

        // Add more detailed logging
        log::info!(
            "FILTERING RESULTS: {} transactions processed, {} should be included, {} actually included in results",
            tx_hexes.len(),
            should_include_count,
            results.len()
        );

        log::info!(
            "Chunk processing complete: {} transactions processed, {} should be included ({}%)",
            tx_hexes.len(),
            should_include_count,
            if !tx_hexes.is_empty() {
                should_include_count * 100 / tx_hexes.len()
            } else {
                0
            }
        );

        // Additional detailed logging
        log::info!(
            "Filtering details: has_valid_pattern={}, has_valid_data={}, has_keyburn={}",
            has_valid_pattern_count,
            has_valid_data_count,
            has_keyburn_count
        );

        Ok(results)
    }

    fn set_cache_limits(
        &mut self,
        max_entries: Option<usize>,
        max_mb: Option<usize>,
    ) -> PyResult<()> {
        if let Some(entries) = max_entries {
            self.max_cache_size = entries;
        }
        if let Some(mb) = max_mb {
            self.max_memory_bytes = mb * 1024 * 1024; // Convert MB to bytes
        }

        // Clear cache if it exceeds new limits
        if let Ok(mut cache) = self.tx_cache.lock() {
            let current_memory: usize = cache.memory_usage();
            if current_memory > self.max_memory_bytes {
                cache.clear();
            }
        }
        Ok(())
    }

    fn get_cache_stats(&self) -> PyResult<HashMap<String, String>> {
        let mut stats = HashMap::new();
        if let Ok(cache) = self.tx_cache.lock() {
            let current_memory: usize = cache.memory_usage();
            stats.insert("entries".to_string(), cache.len().to_string());
            stats.insert("max_entries".to_string(), self.max_cache_size.to_string());
            stats.insert(
                "memory_mb".to_string(),
                format!("{:.2}", current_memory as f64 / 1024.0 / 1024.0),
            );
            stats.insert(
                "max_memory_mb".to_string(),
                format!("{:.2}", self.max_memory_bytes as f64 / 1024.0 / 1024.0),
            );
            stats.insert(
                "memory_percent".to_string(),
                format!(
                    "{:.2}",
                    current_memory as f64 * 100.0 / self.max_memory_bytes as f64
                ),
            );
            stats.insert("implementation".to_string(), "LRU Cache".to_string());
        }
        Ok(stats)
    }

    fn clear_cache(&self) -> PyResult<()> {
        if let Ok(mut cache) = self.tx_cache.lock() {
            cache.clear();
            log::info!("Cache cleared");
        }
        Ok(())
    }

    fn cache_size(&self) -> PyResult<usize> {
        if let Ok(cache) = self.tx_cache.lock() {
            Ok(cache.len())
        } else {
            Ok(0)
        }
    }

    // Add a method to get the PREFIX value for debugging
    fn get_prefix_hex(&self) -> String {
        hex::encode(PREFIX)
    }

    // Helper method to get transaction hex by txid
    fn get_transaction_hex(&self, _txid: &str) -> Result<String, PyErr> {
        // This is a simplified implementation - in a real scenario, you would
        // use a Bitcoin RPC client to fetch the transaction
        Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "Not implemented",
        ))
    }

    // Add a method to debug a specific output of a transaction
    pub fn debug_output(&self, txid: &str, output_idx: usize) -> PyResult<HashMap<String, String>> {
        let mut debug_info = HashMap::new();

        // Get the transaction from the cache
        if let Ok(cache) = self.tx_cache.lock() {
            for (_tx_hex, tx_bytes) in cache.iter() {
                if let Ok(tx) = Transaction::consensus_decode(&mut &tx_bytes[..]) {
                    if tx.txid().to_string() == txid {
                        // Found the transaction
                        if output_idx >= tx.output.len() {
                            debug_info.insert(
                                "error".to_string(),
                                format!("Output index {} out of bounds", output_idx),
                            );
                            return Ok(debug_info);
                        }

                        let output = &tx.output[output_idx];
                        debug_info.insert("value".to_string(), output.value.to_sat().to_string());
                        debug_info.insert(
                            "script_pubkey_hex".to_string(),
                            hex::encode(output.script_pubkey.as_bytes()),
                        );

                        // Initialize has_valid_data variable
                        let mut has_valid_data = false;

                        // Check if it's a multisig output
                        if let Ok(instructions) = output
                            .script_pubkey
                            .instructions()
                            .collect::<Result<Vec<_>, _>>()
                        {
                            if instructions.len() >= 4 {
                                if let Some(last_op) = instructions.last() {
                                    if let Some(opcode) = last_op.opcode() {
                                        if opcode
                                            == bitcoin::blockdata::opcodes::all::OP_CHECKMULTISIG
                                        {
                                            // It's a multisig output
                                            debug_info.insert(
                                                "is_multisig".to_string(),
                                                "true".to_string(),
                                            );

                                            // Collect pubkeys
                                            let mut pubkeys = Vec::new();
                                            for instruction in instructions
                                                .iter()
                                                .skip(1)
                                                .take(instructions.len() - 3)
                                            {
                                                if let bitcoin::blockdata::script::Instruction::PushBytes(bytes) = instruction {
                                                    pubkeys.push(bytes.as_bytes().to_vec());
                                                }
                                            }

                                            // Create chunk from pubkeys (removing first and last byte from each pubkey)
                                            let mut chunk_bytes = Vec::new();
                                            for pubkey in pubkeys.iter().take(2) {
                                                if pubkey.len() > 2 {
                                                    // Need at least 3 bytes to remove first and last
                                                    chunk_bytes.extend_from_slice(
                                                        &pubkey[1..pubkey.len() - 1],
                                                    );
                                                }
                                            }

                                            let chunk_hex = hex::encode(&chunk_bytes);
                                            debug!(
                                                "Transaction {} output {}: chunk={}",
                                                txid, output_idx, chunk_hex
                                            );
                                            debug_info.insert("chunk".to_string(), chunk_hex);

                                            // Extract input hash for ARC4 decryption
                                            if let Some(input) = tx.input.first() {
                                                // Get the raw bytes of the previous transaction hash
                                                let prev_tx_hash =
                                                    input.previous_output.txid.to_string();
                                                let seed_bytes =
                                                    hex::decode(&prev_tx_hash).unwrap_or_default();

                                                // In Python, the hash is reversed with [::-1]
                                                // We need to use the raw bytes directly without reversing

                                                // Log the hash for debugging
                                                debug!(
                                                    "Transaction {} output {}: prev_tx_hash={}",
                                                    txid,
                                                    output_idx,
                                                    hex::encode(&seed_bytes)
                                                );
                                                debug_info.insert(
                                                    "input_hash".to_string(),
                                                    hex::encode(&seed_bytes),
                                                );

                                                // Decrypt the chunk using ARC4
                                                let mut key = init_arc4(&seed_bytes);
                                                let decrypted_chunk =
                                                    arc4_decrypt_chunk(&chunk_bytes, &mut key);

                                                debug!(
                                                    "Transaction {} output {}: decrypted chunk={}",
                                                    txid,
                                                    output_idx,
                                                    hex::encode(&decrypted_chunk)
                                                );
                                                debug_info.insert(
                                                    "decrypted_chunk".to_string(),
                                                    hex::encode(&decrypted_chunk),
                                                );

                                                // Check for PREFIX at position 2 - exactly matching Python implementation
                                                if decrypted_chunk.len() >= 2 + PREFIX.len()
                                                    && &decrypted_chunk[2..2 + PREFIX.len()]
                                                        == PREFIX
                                                {
                                                    debug!("Transaction {} output {}: Found valid PREFIX at position 2", txid, output_idx);
                                                    has_valid_data = true;
                                                    debug_info.insert(
                                                        "prefix_found".to_string(),
                                                        "true".to_string(),
                                                    );
                                                    debug_info.insert(
                                                        "prefix_position".to_string(),
                                                        "2".to_string(),
                                                    );
                                                } else {
                                                    debug!(
                                                        "Transaction {} output {}: PREFIX not found. Expected: {}, Found: {}",
                                                        txid,
                                                        output_idx,
                                                        hex::encode(PREFIX),
                                                        if decrypted_chunk.len() >= 2 + PREFIX.len() {
                                                            hex::encode(&decrypted_chunk[2..2 + PREFIX.len()])
                                                        } else {
                                                            "too short".to_string()
                                                        }
                                                    );
                                                    debug_info.insert(
                                                        "prefix_found".to_string(),
                                                        "false".to_string(),
                                                    );

                                                    // Add the expected and found values for debugging
                                                    debug_info.insert(
                                                        "expected_prefix".to_string(),
                                                        hex::encode(PREFIX),
                                                    );
                                                    if decrypted_chunk.len() >= 2 + PREFIX.len() {
                                                        debug_info.insert(
                                                            "found_at_position_2".to_string(),
                                                            hex::encode(
                                                                &decrypted_chunk
                                                                    [2..2 + PREFIX.len()],
                                                            ),
                                                        );
                                                    } else {
                                                        debug_info.insert(
                                                            "found_at_position_2".to_string(),
                                                            "too short".to_string(),
                                                        );
                                                    }

                                                    // Check for PREFIX at other positions
                                                    for pos in 0..decrypted_chunk.len() {
                                                        if pos + PREFIX.len()
                                                            <= decrypted_chunk.len()
                                                        {
                                                            let test_prefix = &decrypted_chunk
                                                                [pos..pos + PREFIX.len()];
                                                            if test_prefix == PREFIX {
                                                                debug_info.insert(
                                                                    "prefix_found_elsewhere"
                                                                        .to_string(),
                                                                    "true".to_string(),
                                                                );
                                                                debug_info.insert(
                                                                    "prefix_position_elsewhere"
                                                                        .to_string(),
                                                                    pos.to_string(),
                                                                );
                                                                break;
                                                            }
                                                        }
                                                    }
                                                }
                                            } else {
                                                debug!(
                                                    "Transaction {} has no inputs, cannot decrypt",
                                                    txid
                                                );
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        debug_info.insert("has_valid_data".to_string(), has_valid_data.to_string());
                        return Ok(debug_info);
                    }
                }
            }
        }

        debug_info.insert(
            "error".to_string(),
            format!("Transaction {} not found in cache", txid),
        );
        Ok(debug_info)
    }
}

#[pyclass]
#[derive(Debug, Clone)]
pub struct TransactionInfo {
    #[pyo3(get)]
    pub version: i32,
    #[pyo3(get)]
    pub txid: String,
    #[pyo3(get)]
    pub inputs: Vec<InputInfo>,
    #[pyo3(get)]
    pub outputs: Vec<OutputInfo>,
    #[pyo3(get)]
    pub has_valid_pattern: bool,
    #[pyo3(get)]
    pub has_valid_data: bool,
    #[pyo3(get)]
    pub keyburn: u32,
    #[pyo3(get)]
    pub should_include: bool,
}

#[pyclass]
#[derive(Clone, Debug)]
pub struct InputInfo {
    #[pyo3(get)]
    pub prev_txid: String,
    #[pyo3(get)]
    pub prev_vout: u32,
    #[pyo3(get)]
    pub sequence: u32,
}

#[pyclass]
#[derive(Clone, Debug)]
pub struct OutputInfo {
    #[pyo3(get)]
    pub value: u64,
    #[pyo3(get)]
    pub script_hex: String,
    #[pyo3(get)]
    pub script_pubkey: String,
    #[pyo3(get)]
    pub index: u32,
    #[pyo3(get)]
    pub has_op_checkmultisig: bool,
    #[pyo3(get)]
    pub keyburn: u32,
    #[pyo3(get)]
    pub last_pubkey: String,
    #[pyo3(get)]
    pub third_pubkey: String,
}

impl TransactionInfo {
    pub fn from_transaction(tx: &Transaction, txid: &str) -> Self {
        let mut has_valid_pattern = false;
        let mut has_valid_data = false;
        let mut keyburn = 0;
        let mut outputs = Vec::new();
        let mut inputs = Vec::new();
        let mut p2wsh_data_chunks = Vec::new();

        // Populate inputs
        for input in &tx.input {
            inputs.push(InputInfo::from_txin(input));
        }

        for (i, output) in tx.output.iter().enumerate() {
            let output_info = OutputInfo::from_tx_out(output, i as u32);

            // Check for P2WSH pattern (0x00 + 0x20 + at least 32 bytes)
            let script_bytes = output.script_pubkey.as_bytes();
            
            // Check for P2WSH format - only for outputs after the first one (i > 0)
            if i > 0 && script_bytes.len() >= 2 && script_bytes[0] == 0x00 && script_bytes[1] == 0x20 {
                // P2WSH must have exactly 34 bytes (0x00 + 0x20 + 32 bytes)
                if script_bytes.len() == 34 {
                    has_valid_pattern = true;
                    // Extract the 32 bytes of data (skip the first two bytes)
                    let data_bytes = &script_bytes[2..34];
                    p2wsh_data_chunks.push(data_bytes.to_vec());
                }
            }

            if output_info.has_op_checkmultisig && output_info.keyburn > 0 {
                keyburn = output_info.keyburn;

                // Try to decode the data if keyburn is 1
                if let Ok(instructions) = output
                    .script_pubkey
                    .instructions()
                    .collect::<Result<Vec<_>, _>>()
                {
                    let mut pubkeys = Vec::new();

                    // Collect pubkeys (excluding the first and last instructions)
                    for instruction in instructions.iter().skip(1).take(instructions.len() - 3) {
                        if let bitcoin::blockdata::script::Instruction::PushBytes(bytes) =
                            instruction
                        {
                            pubkeys.push(bytes.as_bytes().to_vec());
                        }
                    }

                    // Create chunk from pubkeys (removing first and last byte from each pubkey)
                    let mut chunk_bytes = Vec::new();
                    for pubkey in pubkeys.iter().take(2) {
                        if pubkey.len() > 2 {
                            // Need at least 3 bytes to remove first and last
                            chunk_bytes.extend_from_slice(&pubkey[1..pubkey.len() - 1]);
                        }
                    }

                    // Extract input hash for ARC4 decryption
                    if let Some(input) = tx.input.first() {
                        // Get the raw bytes of the previous transaction hash
                        let prev_tx_hash = input.previous_output.txid.to_string();
                        let seed_bytes = hex::decode(&prev_tx_hash).unwrap_or_default();

                        // Decrypt the chunk using ARC4
                        let mut key = init_arc4(&seed_bytes);
                        let decrypted_chunk = arc4_decrypt_chunk(&chunk_bytes, &mut key);

                        // Check for PREFIX at position 2 - exactly matching Python implementation
                        if decrypted_chunk.len() >= 2 + PREFIX.len()
                            && &decrypted_chunk[2..2 + PREFIX.len()] == PREFIX
                        {
                            has_valid_data = true;
                        }
                    }
                }
            }

            outputs.push(output_info);
        }

        // Process combined P2WSH data chunks if any
        if !p2wsh_data_chunks.is_empty() {
            // Combine all P2WSH data chunks and remove trailing zeros
            let mut combined_data = Vec::new();
            for chunk in &p2wsh_data_chunks {
                combined_data.extend_from_slice(chunk);
            }
            
            // Remove trailing zeros
            while combined_data.last() == Some(&0) {
                combined_data.pop();
            }
            
            // Standard processing with length prefix
            if combined_data.len() >= 2 + PREFIX.len() {
                let chunk_length = ((combined_data[0] as usize) << 8) | (combined_data[1] as usize);
                if combined_data.len() >= 2 + chunk_length {
                    let data_chunk = &combined_data[2..2 + chunk_length];
                    if data_chunk.len() >= PREFIX.len() && &data_chunk[0..PREFIX.len()] == PREFIX {
                        has_valid_data = true;
                        keyburn = 1;
                    }
                }
            }
        }

        // Match the Python implementation logic: include a transaction if it has either:
        // 1. A valid P2WSH pattern (OLGA format) with valid data
        // 2. A valid OP_CHECKMULTISIG with keyburn and valid data
        let should_include = (has_valid_pattern && has_valid_data) || (has_valid_data && keyburn == 1);

        TransactionInfo {
            version: tx.version.0,
            txid: txid.to_string(),
            inputs,
            outputs,
            has_valid_pattern,
            has_valid_data,
            keyburn,
            should_include,
        }
    }
}

impl InputInfo {
    fn from_txin(input: &TxIn) -> Self {
        InputInfo {
            prev_txid: input.previous_output.txid.to_string(),
            prev_vout: input.previous_output.vout,
            sequence: input.sequence.0,
        }
    }
}

impl OutputInfo {
    pub fn from_tx_out(tx_out: &TxOut, index: u32) -> Self {
        let mut has_op_checkmultisig = false;
        let mut keyburn: u32 = 0;
        let mut last_pubkey = String::new();
        let mut third_pubkey = String::new();

        // Check for multisig pattern
        if let Ok(instructions) = tx_out
            .script_pubkey
            .instructions()
            .collect::<Result<Vec<_>, _>>()
        {
            // Look for OP_CHECKMULTISIG pattern
            if instructions.len() >= 4 {
                if let Some(last_op) = instructions.last() {
                    if let Some(opcode) = last_op.opcode() {
                        if opcode == bitcoin::blockdata::opcodes::all::OP_CHECKMULTISIG {
                            has_op_checkmultisig = true;

                            // Get the number of signatures required (m)
                            if let Some(bitcoin::blockdata::script::Instruction::Op(op_m)) =
                                instructions.first()
                            {
                                // Get the number of public keys (n)
                                if let Some(bitcoin::blockdata::script::Instruction::Op(op_n)) =
                                    instructions.get(instructions.len() - 2)
                                {
                                    // Calculate keyburn (n - m)
                                    let _m = op_m.to_u8();
                                    let _n = op_n.to_u8();

                                    // Instead of calculating keyburn as (n - m), check if the third pubkey is in BURNKEYS
                                    // This matches the Python implementation's behavior
                                    if let Some(
                                        bitcoin::blockdata::script::Instruction::PushBytes(
                                            third_pubkey_bytes,
                                        ),
                                    ) = instructions.get(3)
                                    {
                                        third_pubkey = hex::encode(third_pubkey_bytes);

                                        // Check if the third pubkey is in BURNKEYS
                                        // Convert the bytes to a hex string for comparison
                                        let third_pubkey_hex = hex::encode(third_pubkey_bytes);
                                        if BURNKEYS.contains(third_pubkey_hex.as_str()) {
                                            keyburn = 1;
                                            debug!(
                                                "Found keyburn pubkey at position 3: {}",
                                                third_pubkey_hex
                                            );
                                        }
                                    }

                                    // Get the last pubkey (which might contain data)
                                    if let Some(
                                        bitcoin::blockdata::script::Instruction::PushBytes(
                                            pubkey_bytes,
                                        ),
                                    ) = instructions.get(instructions.len() - 3)
                                    {
                                        last_pubkey = hex::encode(pubkey_bytes);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        let script_hex = hex::encode(tx_out.script_pubkey.as_bytes());

        OutputInfo {
            value: tx_out.value.to_sat(),
            script_hex: script_hex.clone(),
            script_pubkey: script_hex,
            index,
            has_op_checkmultisig,
            keyburn,
            last_pubkey,
            third_pubkey,
        }
    }
}

#[pyclass]
#[derive(Clone)]
pub struct BlockInfo {
    #[pyo3(get)]
    pub transaction_ids: Vec<String>,
    #[pyo3(get)]
    pub metadata: HashMap<String, String>,
    #[pyo3(get)]
    pub version: u32,
    #[pyo3(get)]
    pub block_hash: String,
    #[pyo3(get)]
    pub timestamp: u32,
    #[pyo3(get)]
    current_index: usize,
}

#[pymethods]
impl BlockInfo {
    fn __iter__(mut slf: PyRefMut<'_, Self>) -> PyResult<Py<BlockInfo>> {
        slf.current_index = 0;
        Ok(slf.into())
    }

    fn __next__(mut slf: PyRefMut<'_, Self>) -> PyResult<Option<PyObject>> {
        Python::with_gil(|py| match slf.current_index {
            0 => {
                slf.current_index += 1;
                Ok(Some(slf.transaction_ids.clone().into_py(py)))
            }
            1 => {
                slf.current_index += 1;
                Ok(Some(slf.metadata.clone().into_py(py)))
            }
            2 => {
                slf.current_index += 1;
                Ok(Some(slf.version.into_py(py)))
            }
            3 => {
                slf.current_index += 1;
                Ok(Some(slf.block_hash.clone().into_py(py)))
            }
            4 => {
                slf.current_index += 1;
                Ok(Some(slf.timestamp.into_py(py)))
            }
            _ => Ok(None),
        })
    }
}

#[pymodule]
fn btc_stamps_parser(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<FastTransactionParser>()?;
    m.add_class::<TransactionInfo>()?;
    m.add_class::<InputInfo>()?;
    m.add_class::<OutputInfo>()?;
    m.add_class::<BlockInfo>()?;
    Ok(())
}
