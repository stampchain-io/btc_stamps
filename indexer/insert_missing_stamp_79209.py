#!/usr/bin/env python3
"""
Direct insertion of missing stamp 79209 based on verified Counterparty data
"""

import sys
import os
import logging
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pymysql

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Verified data from our investigation
STAMP_NUMBER = 79209
BLOCK_INDEX = 818019
CPID = "A13390036054616082000"
TX_HASH = "95dca4dc27e50e7b26174a0ded7af3b26527def625670d058ae09200eeb3d735"
CREATOR = "bc1qy25gwr9vdrvxx0w35wa9vrpc3hc5h6rd0p56f4"
DESCRIPTION = "STAMP:PGh0bWw+PHN0eWxlPmh0bWwge2JhY2tncm91bmQ6IHVybCgiQTQ1NzI5MjczODk0NzIzNzEwMDAiKSBuby1yZXBlYXQgY2VudGVyIGNlbnRlciBmaXhlZDtiYWNrZ3JvdW5kLXNpemU6IGNvbnRhaW47aGVpZ2h0OiAxMDAlO292ZXJmbG93OiBoaWRkZW47fTwvc3R5bGU+PC9odG1sPg=="
BASE64_DATA = "PGh0bWw+PHN0eWxlPmh0bWwge2JhY2tncm91bmQ6IHVybCgiQTQ1NzI5MjczODk0NzIzNzEwMDAiKSBuby1yZXBlYXQgY2VudGVyIGNlbnRlciBmaXhlZDtiYWNrZ3JvdW5kLXNpemU6IGNvbnRhaW47aGVpZ2h0OiAxMDAlO292ZXJmbG93OiBoaWRkZW47fTwvc3R5bGU+PC9odG1sPg=="

def connect_to_database():
    """Connect to the database"""
    db_config = {
        'host': os.environ.get("RDS_HOSTNAME", "localhost"),
        'port': int(os.environ.get("RDS_PORT", 3306)),
        'user': os.environ.get("RDS_USER") or os.environ.get("MYSQL_USER", "admin"),
        'password': os.environ.get("RDS_PASSWORD") or os.environ.get("MYSQL_PASSWORD", "password"),
        'database': os.environ.get("RDS_DATABASE", "btc_stamps"),
        'charset': 'utf8mb4'
    }
    
    logger.info(f"Connecting to database: {db_config['host']}:{db_config['port']}")
    return pymysql.connect(**db_config)

def verify_problem_exists():
    """Verify the stamp is missing and transaction exists"""
    conn = connect_to_database()
    cursor = conn.cursor()
    
    # Check transaction exists
    cursor.execute("SELECT tx_index, block_time FROM transactions WHERE tx_hash = %s", (TX_HASH,))
    tx_result = cursor.fetchone()
    if not tx_result:
        logger.error("Transaction not found in database!")
        cursor.close()
        conn.close()
        return False, None, None
    
    tx_index, block_time = tx_result
    logger.info(f"Transaction found: tx_index={tx_index}, block_time={block_time}")
    
    # Check stamp does not exist
    cursor.execute("SELECT COUNT(*) FROM StampTableV4 WHERE stamp = %s OR cpid = %s", (STAMP_NUMBER, CPID))
    stamp_exists = cursor.fetchone()[0] > 0
    
    if stamp_exists:
        logger.info("Stamp already exists - no need to insert")
        cursor.close()
        conn.close()
        return False, None, None
    
    cursor.close()
    conn.close()
    logger.info("Consensus mismatch confirmed - stamp missing")
    return True, tx_index, block_time

def get_stamp_table_schema():
    """Get the schema for StampTableV4 to know what fields are required"""
    conn = connect_to_database()
    cursor = conn.cursor()
    
    cursor.execute("DESCRIBE StampTableV4")
    columns = cursor.fetchall()
    
    logger.info("StampTableV4 schema:")
    for column in columns:
        logger.info(f"  {column[0]} - {column[1]} - {'NULL' if column[2] == 'YES' else 'NOT NULL'}")
    
    cursor.close()
    conn.close()
    return columns

def insert_missing_stamp(tx_index, block_time):
    """Insert the missing stamp into the database"""
    logger.info("=== Inserting Missing Stamp ===")
    
    conn = connect_to_database()
    cursor = conn.cursor()
    
    try:
        # Decode the base64 to determine content
        decoded_data = base64.b64decode(BASE64_DATA)
        logger.info(f"Decoded data preview: {decoded_data[:100]}...")
        
        # Determine MIME type based on content
        mime_type = ""
        if decoded_data.startswith(b'<html'):
            mime_type = "text/html"
        elif decoded_data.startswith(b'<!DOCTYPE'):
            mime_type = "text/html"
        
        logger.info(f"Detected MIME type: {mime_type}")
        
        # Insert the stamp with correct schema fields
        insert_query = """
            INSERT INTO StampTableV4 (
                stamp, block_index, cpid, asset_longname, 
                creator, divisible, keyburn, locked,
                message_index, stamp_base64, stamp_mimetype, 
                stamp_url, supply, block_time, tx_hash, 
                tx_index, src_data, ident, stamp_hash,
                is_btc_stamp, is_reissue, file_hash, is_valid_base64,
                file_size_bytes
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s
            )
        """
        
        # Calculate some derived values
        is_btc_stamp = 1         # This is a STAMP
        is_reissue = 0           # Not a reissue
        is_valid_base64 = 1      # Valid base64 (we verified this)
        file_size_bytes = len(decoded_data)  # Size of decoded data
        
        # Create a hash for the stamp content
        import hashlib
        file_hash = hashlib.sha256(decoded_data).hexdigest()
        stamp_hash = hashlib.sha256(f"{STAMP_NUMBER}{CPID}".encode()).hexdigest()
        
        # Convert block_time to datetime format if needed
        from datetime import datetime
        if isinstance(block_time, int):
            block_time_dt = datetime.fromtimestamp(block_time)
        else:
            block_time_dt = block_time
        
        # Create JSON data for src_data field
        import json
        src_data_json = json.dumps({
            "description": DESCRIPTION,
            "asset": CPID,
            "quantity": 500,
            "divisible": False,
            "locked": True,
            "source": CREATOR,
            "issuer": CREATOR
        })
        
        values = (
            STAMP_NUMBER,      # stamp
            BLOCK_INDEX,       # block_index  
            CPID,              # cpid
            None,              # asset_longname
            CREATOR,           # creator
            0,                 # divisible (False)
            1,                 # keyburn (True)
            1,                 # locked (True)
            0,                 # message_index
            BASE64_DATA,       # stamp_base64
            mime_type,         # stamp_mimetype
            None,              # stamp_url
            500,               # supply (from CP data)
            block_time_dt,     # block_time
            TX_HASH,           # tx_hash
            tx_index,          # tx_index
            src_data_json,     # src_data (JSON format)
            "STAMP",           # ident
            stamp_hash,        # stamp_hash
            is_btc_stamp,      # is_btc_stamp
            is_reissue,        # is_reissue
            file_hash,         # file_hash
            is_valid_base64,   # is_valid_base64
            file_size_bytes    # file_size_bytes
        )
        
        logger.info(f"Inserting stamp {STAMP_NUMBER} with CPID {CPID}")
        
        cursor.execute(insert_query, values)
        conn.commit()
        
        logger.info("✅ Stamp inserted successfully!")
        
        # Verify insertion
        cursor.execute("SELECT stamp, cpid, creator, block_index FROM StampTableV4 WHERE stamp = %s", (STAMP_NUMBER,))
        result = cursor.fetchone()
        
        if result:
            stamp, cpid, creator, block = result
            logger.info(f"Verification: stamp={stamp}, cpid={cpid}, creator={creator}, block={block}")
        else:
            logger.error("Insertion failed - stamp not found after insert")
            
    except Exception as e:
        logger.error(f"Error inserting stamp: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def main():
    """Main function"""
    logger.info(f"Starting manual insertion of missing stamp {STAMP_NUMBER}")
    
    # Step 1: Get table schema to understand structure
    get_stamp_table_schema()
    
    # Step 2: Verify the problem exists
    needs_fix, tx_index, block_time = verify_problem_exists()
    if not needs_fix:
        logger.info("No fix needed")
        return
    
    # Step 3: Insert the missing stamp
    insert_missing_stamp(tx_index, block_time)
    
    logger.info("✅ Manual stamp insertion complete!")

if __name__ == "__main__":
    main()