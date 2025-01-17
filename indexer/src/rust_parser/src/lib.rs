use pyo3::prelude::*;
use bitcoin::consensus::Decodable;
use bitcoin::{Block, Transaction, TxOut, TxIn};
use std::collections::HashMap;
use std::sync::Mutex;
use rayon::prelude::*;
use log::error;

#[pyclass]
pub struct FastTransactionParser {
    tx_cache: Mutex<HashMap<String, Vec<u8>>>,
}

#[pymethods]
impl FastTransactionParser {
    #[new]
    fn new() -> Self {
        FastTransactionParser {
            tx_cache: Mutex::new(HashMap::new()),
        }
    }

    fn deserialize_transaction(&self, tx_hex: &str) -> PyResult<TransactionInfo> {
        // Log the length of the transaction hex string
        log::debug!("Deserializing transaction with hex length: {}", tx_hex.len());

        // Check cache first
        if let Ok(cache) = self.tx_cache.lock() {
            if let Some(cached_tx) = cache.get(tx_hex) {
                if let Ok(tx) = Transaction::consensus_decode(&mut &cached_tx[..]) {
                    return Ok(TransactionInfo::from_transaction(&tx));
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

        // Cache the raw bytes
        if let Ok(mut cache) = self.tx_cache.lock() {
            cache.insert(tx_hex.to_string(), tx_bytes);
        }

        Ok(TransactionInfo::from_transaction(&tx))
    }

    fn parse_block(&self, block_hex: &str) -> PyResult<BlockInfo> {
        let block_bytes = hex::decode(block_hex).map_err(|e| {
            error!("Failed to decode block hex: {}", e);
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
        })?;

        let block = Block::consensus_decode(&mut &block_bytes[..]).map_err(|e| {
            error!("Failed to decode block: {}", e);
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid block: {}", e))
        })?;

        Ok(BlockInfo::from_block(&block))
    }

    fn batch_parse_transactions(&self, tx_hexes: Vec<&str>) -> PyResult<Vec<TransactionInfo>> {
        tx_hexes.par_iter()
            .map(|&tx_hex| {
                let tx_bytes = hex::decode(tx_hex).map_err(|e| {
                    error!("Failed to decode hex in batch: {}", e);
                    PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
                })?;

                let tx = Transaction::consensus_decode(&mut &tx_bytes[..]).map_err(|e| {
                    error!("Failed to decode transaction in batch: {}", e);
                    PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid transaction: {}", e))
                })?;

                // Cache the result
                if let Ok(mut cache) = self.tx_cache.lock() {
                    cache.insert(tx_hex.to_string(), tx_bytes);
                }

                Ok(TransactionInfo::from_transaction(&tx))
            })
            .collect()
    }

    fn clear_cache(&self) -> PyResult<()> {
        if let Ok(mut cache) = self.tx_cache.lock() {
            cache.clear();
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
}

#[pyclass]
#[derive(Clone)]
pub struct TransactionInfo {
    #[pyo3(get)]
    pub txid: String,
    #[pyo3(get)]
    pub version: i32,
    #[pyo3(get)]
    pub inputs: Vec<InputInfo>,
    #[pyo3(get)]
    pub outputs: Vec<OutputInfo>,
    #[pyo3(get)]
    pub hex: String,
}

#[pyclass]
#[derive(Clone)]
pub struct InputInfo {
    #[pyo3(get)]
    pub prev_txid: String,
    #[pyo3(get)]
    pub prev_vout: u32,
    #[pyo3(get)]
    pub sequence: u32,
}

#[pyclass]
#[derive(Clone)]
pub struct OutputInfo {
    #[pyo3(get)]
    pub value: i64,
    #[pyo3(get)]
    pub script_pubkey: String,
    #[pyo3(get)]
    pub is_op_return: bool,
}

#[pyclass]
#[derive(Clone)]
pub struct BlockInfo {
    #[pyo3(get)]
    pub block_hash: String,
    #[pyo3(get)]
    pub prev_block_hash: String,
    #[pyo3(get)]
    pub merkle_root: String,
    #[pyo3(get)]
    pub timestamp: u32,
    #[pyo3(get)]
    pub transactions: Vec<TransactionInfo>,
}

impl TransactionInfo {
    fn from_transaction(tx: &Transaction) -> Self {
        TransactionInfo {
            txid: tx.txid().to_string(),
            version: tx.version.0 as i32,
            inputs: tx.input.iter().map(InputInfo::from_txin).collect(),
            outputs: tx.output.iter().map(OutputInfo::from_txout).collect(),
            hex: hex::encode(bitcoin::consensus::serialize(tx)),
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
    fn from_txout(output: &TxOut) -> Self {
        let script = &output.script_pubkey;
        OutputInfo {
            value: output.value.to_sat() as i64,
            script_pubkey: hex::encode(script.as_bytes()),
            is_op_return: script.is_op_return(),
        }
    }
}

impl BlockInfo {
    fn from_block(block: &Block) -> Self {
        BlockInfo {
            block_hash: block.block_hash().to_string(),
            prev_block_hash: block.header.prev_blockhash.to_string(),
            merkle_root: block.header.merkle_root.to_string(),
            timestamp: block.header.time,
            transactions: block.txdata.iter().map(TransactionInfo::from_transaction).collect(),
        }
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