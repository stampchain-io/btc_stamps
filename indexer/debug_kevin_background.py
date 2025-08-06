#!/usr/bin/env python3
"""Debug script to check KEVIN token background image generation"""

import hashlib
import json
import os
import sys
from io import BytesIO

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from index_core.database import get_srcbackground_data
from index_core.database_manager import DatabaseManager
from index_core.src20 import build_src20_svg_string


def main():
    # Connect to database
    db_manager = DatabaseManager()
    db = db_manager.connect()

    try:
        # Query srcbackground table for KEVIN
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT tick, base64, font_size, text_color
                FROM srcbackground
                WHERE UPPER(tick) = 'KEVIN'
            """
            )
            result = cursor.fetchone()

            if result:
                print("Found KEVIN in srcbackground table:")
                print(f"  tick: {result[0]}")
                print(f"  base64: {result[1][:100]}..." if result[1] else None)
                print(f"  font_size: {result[2]}")
                print(f"  text_color: {result[3]}")
            else:
                print("KEVIN not found in srcbackground table")

        # Get srcbackground data using the function
        background_base64, font_size, text_color = get_srcbackground_data(db, "KEVIN")
        print(f"\nget_srcbackground_data result:")
        print(f"  background_base64: {background_base64[:100] if background_base64 else None}...")
        print(f"  font_size: {font_size}")
        print(f"  text_color: {text_color}")

        # Create a sample SRC-20 dict for KEVIN deploy
        src20_dict = {"p": "src-20", "op": "deploy", "tick": "KEVIN", "max": "21000000", "lim": "1000"}

        # Generate SVG
        svg_data = build_src20_svg_string(db, src20_dict)
        print(f"\nGenerated SVG length: {len(svg_data)} bytes")
        print(f"SVG preview: {svg_data[:200].decode('utf-8') if isinstance(svg_data, bytes) else svg_data[:200]}...")

        # Calculate MD5
        if isinstance(svg_data, bytes):
            md5_hash = hashlib.md5(svg_data).hexdigest()
        else:
            md5_hash = hashlib.md5(svg_data.encode("utf-8")).hexdigest()
        print(f"\nMD5 hash of generated SVG: {md5_hash}")

        # Check S3 objects cache
        import config

        filename = "23765f9bc6b87e078b1f93ed213f90b9004998336575f726e46f34ddbea5e5f3.svg"
        s3_path = f"{config.AWS_S3_IMAGE_DIR}{filename}"

        if s3_path in config.S3_OBJECTS:
            print(f"\nFound in S3_OBJECTS cache:")
            print(f"  MD5: {config.S3_OBJECTS[s3_path]['md5']}")
        else:
            print(f"\nNot found in S3_OBJECTS cache")

        # Save generated SVG to file for comparison
        output_file = "/home/ubuntu/stampsdev/btc_stamps/indexer/kevin_generated.svg"
        with open(output_file, "wb") as f:
            f.write(svg_data if isinstance(svg_data, bytes) else svg_data.encode("utf-8"))
        print(f"\nSaved generated SVG to: {output_file}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
