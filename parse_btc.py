from bitcoinlib.blocks import Block
from indexing.parse_stamp import process_tx

def parse_block(block_hash):
    block = Block.from_hash(block_hash)
    block_height = block.height
    txs = block.txs
    parsed_txs = []
    for tx in txs:
        parsed_tx = process_tx(tx, block_height)
        if parsed_tx:
            parsed_txs.append(parsed_tx)
    return parsed_txs