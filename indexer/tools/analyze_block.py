from index_core.backend import Backend
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_block():
    backend = None
    try:
        backend = Backend()
        block_hash = backend.rpc("getblockhash", [882044])
        block = backend.rpc("getblock", [block_hash, 2])
        
        stamp_count = 0
        total_count = len(block["tx"])
        
        for tx in block["tx"]:
            is_stamp = False
            for vout in tx["vout"]:
                script = vout.get("scriptPubKey", {})
                script_type = script.get("type")
                script_asm = script.get("asm", "")
                script_hex = script.get("hex", "")
                
                if (script_type == "nulldata" or 
                    "OP_RETURN" in script_asm or
                    "OP_CHECKMULTISIG" in script_asm or
                    script_type == "witness_v0_scripthash" or
                    (script_hex and script_hex.startswith("0020"))):  # P2WSH pattern
                    
                    print(f"\nFound potential stamp transaction:")
                    print(f"TXID: {tx['txid']}")
                    print(f"Script type: {script_type}")
                    print(f"Script hex: {script_hex}")
                    print(f"Script asm: {script_asm}\n")
                    is_stamp = True
                    break
            
            if is_stamp:
                stamp_count += 1
        
        print(f"\nSummary:")
        print(f"Total transactions: {total_count}")
        print(f"Stamp transactions: {stamp_count}")
        print(f"Filter rate: {((total_count - stamp_count) / total_count * 100):.1f}%")
        
    except Exception as e:
        print(f"Error analyzing block: {e}")

if __name__ == "__main__":
    analyze_block()
