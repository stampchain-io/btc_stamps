use pyo3::prelude::*;
use bitcoin::consensus::{Decodable, Encodable};
use bitcoin::{Block, Transaction, Script, TxOut, TxIn};
use std::collections::HashMap;
use rayon::prelude::*;

#[pyclass]
pub struct FastTransactionParser {
    #[pyo3(get)]
    pub tx_cache: HashMap<String, Vec<u8>>,
}

#[pymethods]
impl FastTransactionParser {
    #[new]
    fn new() -> Self {
        FastTransactionParser {
            tx_cache: HashMap::new(),
        }
    }

    fn deserialize_transaction(&mut self, tx_hex: &str) -> PyResult<TransactionInfo> {
        // Check cache first
        if let Some(cached_tx) = self.tx_cache.get(tx_hex) {
            if let Ok(tx) = Transaction::consensus_decode(&mut &cached_tx[..]) {
                return Ok(TransactionInfo::from_transaction(&tx));
            }
        }

        // Parse hex and cache result
        let tx_bytes = hex::decode(tx_hex).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
        })?;

        let tx = Transaction::consensus_decode(&mut &tx_bytes[..])
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid transaction: {}", e)))?;

        // Cache the raw bytes
        self.tx_cache.insert(tx_hex.to_string(), tx_bytes);

        Ok(TransactionInfo::from_transaction(&tx))
    }

    fn parse_block(&self, block_hex: &str) -> PyResult<BlockInfo> {
        let block_bytes = hex::decode(block_hex).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
        })?;

        let block = Block::consensus_decode(&mut &block_bytes[..])
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid block: {}", e)))?;

        Ok(BlockInfo::from_block(&block))
    }

    fn batch_parse_transactions(&self, tx_hexes: Vec<&str>) -> PyResult<Vec<TransactionInfo>> {
        tx_hexes.par_iter()
            .map(|&tx_hex| {
                let tx_bytes = hex::decode(tx_hex).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid hex: {}", e))
                })?;

                let tx = Transaction::consensus_decode(&mut &tx_bytes[..])
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid transaction: {}", e)))?;

                Ok(TransactionInfo::from_transaction(&tx))
            })
            .collect()
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
            version: tx.version,
            inputs: tx.input.iter().map(InputInfo::from_txin).collect(),
            outputs: tx.output.iter().map(OutputInfo::from_txout).collect(),
        }
    }
}

impl InputInfo {
    fn from_txin(input: &TxIn) -> Self {
        InputInfo {
            prev_txid: input.previous_output.txid.to_string(),
            prev_vout: input.previous_output.vout,
            sequence: input.sequence,
        }
    }
}

impl OutputInfo {
    fn from_txout(output: &TxOut) -> Self {
        let script = &output.script_pubkey;
        OutputInfo {
            value: output.value,
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