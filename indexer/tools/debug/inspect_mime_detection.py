#!/usr/bin/env python3
"""
Debug script to inspect MIME type detection for stamp transactions
and analyze why certain content types are misclassified
"""

import argparse
import asyncio
import base64
import logging
import os
import sys

import magic
import regex as re

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.index_core.backend import Backend
from src.index_core.base64_utils import parse_base64_from_description

# Import necessary modules
from src.index_core.fetch_utils import fetch_xcp_async
from src.index_core.node_health import update_healthy_nodes

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize backend instance
backend_instance = Backend()


def is_html_content(content_bytes):
    """
    Enhanced HTML detection logic
    """
    try:
        content_str = content_bytes.decode("utf-8", errors="ignore").strip().lower()

        # Check for HTML doctype
        if content_str.startswith("<!doctype html"):
            return True

        # Check for HTML tags
        html_patterns = [
            r"<html[^>]*>",
            r"<head[^>]*>",
            r"<body[^>]*>",
            r"<title[^>]*>",
            r"<meta[^>]*>",
            r"<div[^>]*>",
            r"<p[^>]*>",
            r"<span[^>]*>",
            r"<h[1-6][^>]*>",
            r"<script[^>]*>",
            r"<style[^>]*>",
            r"<link[^>]*>",
        ]

        for pattern in html_patterns:
            if re.search(pattern, content_str):
                return True

        # Check for common HTML structure
        if "<" in content_str and ">" in content_str:
            # Count tag-like structures
            tag_count = len(re.findall(r"<[^>]+>", content_str))
            if tag_count >= 2:  # At least 2 tags suggest HTML
                return True

        return False
    except Exception:
        return False


def is_javascript_content(content_bytes):
    """
    Enhanced JavaScript detection logic
    """
    try:
        content_str = content_bytes.decode("utf-8", errors="ignore")

        js_patterns = [
            r"\bfunction\s+\w+\s*\(",
            r"\bvar\s+\w+\s*=",
            r"\blet\s+\w+\s*=",
            r"\bconst\s+\w+\s*=",
            r"\bif\s*\(.*?\)\s*{",
            r"\bfor\s*\(.*?\)\s*{",
            r"\bwhile\s*\(.*?\)\s*{",
            r"\bclass\s+\w+\s*{",
            r"\breturn\s+",
            r"\b=>\s*{",
            r"console\.log\(",
            r"document\.",
            r"window\.",
        ]

        for pattern in js_patterns:
            if re.search(pattern, content_str, re.IGNORECASE):
                return True

        return False
    except Exception:
        return False


def is_css_content(content_bytes):
    """
    Enhanced CSS detection logic
    """
    try:
        content_str = content_bytes.decode("utf-8", errors="ignore")

        css_patterns = [
            r"[.#]?\w+\s*{[^}]*}",  # CSS rules
            r"@media\s*\([^)]*\)",  # Media queries
            r"@import\s+",  # Import statements
            r"@font-face\s*{",  # Font face declarations
            r":\s*[^;]+;",  # Property declarations
            r"color\s*:\s*#?[a-fA-F0-9]{3,6}",  # Color properties
            r"font-family\s*:",  # Font family
            r"background\s*:",  # Background properties
        ]

        for pattern in css_patterns:
            if re.search(pattern, content_str, re.IGNORECASE):
                return True

        return False
    except Exception:
        return False


def enhanced_mime_detection(content_bytes, original_mime=None):
    """
    Enhanced MIME type detection with custom logic
    """
    results = {"original_magic": original_mime, "enhanced_detection": None, "confidence": "low", "reasons": []}

    # Try magic detection first
    try:
        magic_mime = magic.from_buffer(content_bytes, mime=True)
        results["original_magic"] = magic_mime
    except Exception as e:
        results["reasons"].append(f"Magic detection failed: {e}")

    # Enhanced detection logic
    if is_html_content(content_bytes):
        results["enhanced_detection"] = "text/html"
        results["confidence"] = "high"
        results["reasons"].append("HTML tags and structure detected")
    elif is_javascript_content(content_bytes):
        results["enhanced_detection"] = "application/javascript"
        results["confidence"] = "high"
        results["reasons"].append("JavaScript syntax detected")
    elif is_css_content(content_bytes):
        results["enhanced_detection"] = "text/css"
        results["confidence"] = "high"
        results["reasons"].append("CSS syntax detected")
    else:
        # Try to decode as text
        try:
            content_str = content_bytes.decode("utf-8")
            if content_str.isprintable() or all(ord(c) < 128 for c in content_str):
                results["enhanced_detection"] = "text/plain"
                results["confidence"] = "medium"
                results["reasons"].append("Valid UTF-8 text content")
            else:
                results["enhanced_detection"] = "application/octet-stream"
                results["confidence"] = "low"
                results["reasons"].append("Binary or non-printable content")
        except UnicodeDecodeError:
            results["enhanced_detection"] = "application/octet-stream"
            results["confidence"] = "medium"
            results["reasons"].append("Non-UTF-8 binary content")

    return results


def parse_p2wsh_outputs(tx_hex, block_index):
    """
    Parse P2WSH outputs from raw transaction hex to extract stamp data
    """
    try:
        # Deserialize the transaction
        ctx = backend_instance.deserialize(tx_hex)

        p2wsh_data_chunks = []

        # Process each output
        for idx, vout in enumerate(ctx.vout):
            try:
                # Get the script from the output
                script_bytes = bytes.fromhex(vout.scriptPubKey.hex())

                # Check for P2WSH pattern (0x00 + exactly 32 bytes)
                if len(script_bytes) >= 33 and script_bytes[0] == 0x00 and script_bytes[1] == 0x20:
                    data_bytes = script_bytes[2:34]  # Get the 32 bytes of data
                    p2wsh_data_chunks.append(data_bytes)
                    print(f"Found P2WSH output at index {idx}: {data_bytes.hex()}")

            except Exception as e:
                print(f"Error processing output {idx}: {e}")
                continue

        if not p2wsh_data_chunks:
            return None

        # Combine all P2WSH data chunks
        combined_data = b"".join(p2wsh_data_chunks).rstrip(b"\x00")  # Remove padding zeros

        print(f"Combined P2WSH data: {len(combined_data)} bytes")
        print(f"Combined data (hex): {combined_data.hex()}")

        # Check if combined data has the length prefix
        if len(combined_data) >= 2:
            # Extract the length prefix (first 2 bytes)
            chunk_length = int.from_bytes(combined_data[:2], byteorder="big")
            print(f"Data length from prefix: {chunk_length}")

            # Ensure that combined_data has enough bytes
            if len(combined_data) >= 2 + chunk_length:
                # Extract the data chunk
                data_chunk = combined_data[2 : 2 + chunk_length]
                print(f"Extracted data chunk: {data_chunk.hex()}")

                # For P2WSH, the data chunk IS the content (no STAMP: prefix expected)
                print(f"P2WSH raw content: {len(data_chunk)} bytes")
                return data_chunk
            else:
                print(f"Not enough data: expected {2 + chunk_length}, got {len(combined_data)}")
        else:
            print(f"Data too short for length prefix: {len(combined_data)} < 2")

        return None

    except Exception as e:
        print(f"Error parsing P2WSH outputs: {e}")
        return None


async def setup_cp_api():
    """Initialize CP API and nodes"""
    update_healthy_nodes()
    logger.info("CP API initialized")


async def fetch_transaction_details(tx_hash):
    """Fetch detailed transaction information from CP API"""
    logger.info(f"Fetching transaction details for {tx_hash}...")

    endpoint = f"/transactions/{tx_hash}"
    tx_data = await fetch_xcp_async(endpoint)

    if not tx_data or "result" not in tx_data:
        logger.error(f"Failed to fetch transaction details for {tx_hash}")
        return None

    return tx_data["result"]


async def fetch_raw_transaction(tx_hash):
    """Fetch raw transaction hex"""
    try:
        tx_hex = backend_instance.getrawtransaction(tx_hash, verbose=False)
        return tx_hex
    except Exception as e:
        print(f"Failed to fetch raw transaction: {e}")
        return None


def analyze_stamp_content(tx_info, tx_hash, tx_hex, block_index):
    """Analyze the stamp content and MIME detection"""
    print(f"\n{'='*80}")
    print(f"ANALYZING TRANSACTION: {tx_hash}")
    print(f"Block Index: {block_index}")
    print(f"{'='*80}")

    found_stamp_data = False

    # Check if transaction has issuances (Counterparty stamps)
    if "issuances" in tx_info and tx_info["issuances"]:
        print("\n--- COUNTERPARTY ISSUANCE FOUND ---")
        issuance = tx_info["issuances"][0]

        description = issuance.get("description", "")
        print(f"Description: {description}")

        if description and "stamp:" in description.lower():
            print("✓ Contains 'stamp:' prefix")
            found_stamp_data = True

            # Parse base64 from description
            try:
                base64_string, mime_hint = parse_base64_from_description(description)
                print(f"MIME hint from description: {mime_hint}")
                print(f"Base64 string length: {len(base64_string) if base64_string else 0}")

                if base64_string:
                    # Decode base64
                    try:
                        decoded_content = base64.b64decode(base64_string)
                        print(f"Decoded content size: {len(decoded_content)} bytes")

                        # Show first 200 characters as preview
                        try:
                            preview = decoded_content.decode("utf-8", errors="ignore")[:200]
                            print(f"Content preview: {repr(preview)}")
                        except Exception:
                            print(f"Content preview (hex): {decoded_content[:50].hex()}")

                        # Original magic detection
                        try:
                            original_mime = magic.from_buffer(decoded_content, mime=True)
                            print(f"Original magic MIME: {original_mime}")
                        except Exception as e:
                            original_mime = None
                            print(f"Original magic failed: {e}")

                        # Enhanced detection
                        enhanced_results = enhanced_mime_detection(decoded_content, original_mime)

                        print("\n--- MIME DETECTION ANALYSIS ---")
                        print(f"Original magic result: {enhanced_results['original_magic']}")
                        print(f"Enhanced detection: {enhanced_results['enhanced_detection']}")
                        print(f"Confidence: {enhanced_results['confidence']}")
                        print(f"Reasons: {', '.join(enhanced_results['reasons'])}")

                        # Determine file suffix
                        if enhanced_results["enhanced_detection"]:
                            suffix = enhanced_results["enhanced_detection"].split("/")[-1]
                            # Apply suffix mapping
                            suffix_map = {"svg+xml": "svg", "plain": "txt", "xhtml+xml": "html", "javascript": "js"}
                            suffix = suffix_map.get(suffix, suffix)
                            print(f"Recommended file suffix: {suffix}")

                        # Check if this would be misclassified
                        if (
                            enhanced_results["original_magic"] == "application/octet-stream"
                            and enhanced_results["enhanced_detection"] != "application/octet-stream"
                        ):
                            print("\n⚠️  MISCLASSIFICATION DETECTED!")
                            print(f"   Magic detected: {enhanced_results['original_magic']}")
                            print(f"   Should be: {enhanced_results['enhanced_detection']}")

                    except Exception as e:
                        print(f"Failed to decode base64: {e}")

            except Exception as e:
                print(f"Failed to parse description: {e}")
        else:
            print("✗ No 'stamp:' prefix found")

    # Check for direct data field (non-Counterparty stamps)
    data = tx_info.get("data", "")
    if data and "5354414d503a" in data:  # "STAMP:" in hex
        print("\n--- DIRECT STAMP DATA FOUND ---")
        print("Data field contains STAMP: prefix")
        print(f"Data length: {len(data)} characters")
        found_stamp_data = True

        # Try to extract and analyze the STAMP data
        try:
            # Convert hex data to bytes
            data_bytes = bytes.fromhex(data)

            # Look for STAMP: prefix
            stamp_prefix = b"STAMP:"
            if stamp_prefix in data_bytes:
                # Extract data after STAMP: prefix
                stamp_start = data_bytes.find(stamp_prefix) + len(stamp_prefix)
                stamp_data = data_bytes[stamp_start:]

                print(f"Raw stamp data size: {len(stamp_data)} bytes")

                # Try to decode as base64
                try:
                    # The stamp data might be base64 encoded
                    decoded_content = base64.b64decode(stamp_data)
                    print(f"Decoded content size: {len(decoded_content)} bytes")

                    # Show preview
                    try:
                        preview = decoded_content.decode("utf-8", errors="ignore")[:200]
                        print(f"Content preview: {repr(preview)}")
                    except Exception:
                        print(f"Content preview (hex): {decoded_content[:50].hex()}")

                    # Original magic detection
                    try:
                        original_mime = magic.from_buffer(decoded_content, mime=True)
                        print(f"Original magic MIME: {original_mime}")
                    except Exception as e:
                        original_mime = None
                        print(f"Original magic failed: {e}")

                    # Enhanced detection
                    enhanced_results = enhanced_mime_detection(decoded_content, original_mime)

                    print("\n--- MIME DETECTION ANALYSIS ---")
                    print(f"Original magic result: {enhanced_results['original_magic']}")
                    print(f"Enhanced detection: {enhanced_results['enhanced_detection']}")
                    print(f"Confidence: {enhanced_results['confidence']}")
                    print(f"Reasons: {', '.join(enhanced_results['reasons'])}")

                    # Determine file suffix
                    if enhanced_results["enhanced_detection"]:
                        suffix = enhanced_results["enhanced_detection"].split("/")[-1]
                        # Apply suffix mapping
                        suffix_map = {"svg+xml": "svg", "plain": "txt", "xhtml+xml": "html", "javascript": "js"}
                        suffix = suffix_map.get(suffix, suffix)
                        print(f"Recommended file suffix: {suffix}")

                    # Check if this would be misclassified
                    if (
                        enhanced_results["original_magic"] == "application/octet-stream"
                        and enhanced_results["enhanced_detection"] != "application/octet-stream"
                    ):
                        print("\n⚠️  MISCLASSIFICATION DETECTED!")
                        print(f"   Magic detected: {enhanced_results['original_magic']}")
                        print(f"   Should be: {enhanced_results['enhanced_detection']}")

                except Exception as e:
                    print(f"Failed to decode as base64: {e}")
                    # Try to analyze raw stamp data
                    try:
                        preview = stamp_data.decode("utf-8", errors="ignore")[:200]
                        print(f"Raw stamp data preview: {repr(preview)}")
                    except Exception:
                        print(f"Raw stamp data (hex): {stamp_data[:50].hex()}")
            else:
                print("STAMP: prefix not found in decoded data")

        except Exception as e:
            print(f"Failed to analyze direct stamp data: {e}")

    # Check for P2WSH outputs (this is likely where the data is!)
    if tx_hex:
        print("\n--- CHECKING P2WSH OUTPUTS ---")
        p2wsh_data = parse_p2wsh_outputs(tx_hex, block_index)

        if p2wsh_data:
            print("✓ Found P2WSH stamp data!")
            found_stamp_data = True

            # Try to decode as base64 first
            try:
                decoded_content = base64.b64decode(p2wsh_data)
                print(f"P2WSH decoded content size: {len(decoded_content)} bytes")

                # Show preview
                try:
                    preview = decoded_content.decode("utf-8", errors="ignore")[:200]
                    print(f"P2WSH content preview: {repr(preview)}")
                except Exception:
                    print(f"P2WSH content preview (hex): {decoded_content[:50].hex()}")

                # Original magic detection
                try:
                    original_mime = magic.from_buffer(decoded_content, mime=True)
                    print(f"P2WSH original magic MIME: {original_mime}")
                except Exception as e:
                    original_mime = None
                    print(f"P2WSH original magic failed: {e}")

                # Enhanced detection
                enhanced_results = enhanced_mime_detection(decoded_content, original_mime)

                print("\n--- P2WSH MIME DETECTION ANALYSIS (BASE64 DECODED) ---")
                print(f"Original magic result: {enhanced_results['original_magic']}")
                print(f"Enhanced detection: {enhanced_results['enhanced_detection']}")
                print(f"Confidence: {enhanced_results['confidence']}")
                print(f"Reasons: {', '.join(enhanced_results['reasons'])}")

                # Determine file suffix
                if enhanced_results["enhanced_detection"]:
                    suffix = enhanced_results["enhanced_detection"].split("/")[-1]
                    # Apply suffix mapping
                    suffix_map = {"svg+xml": "svg", "plain": "txt", "xhtml+xml": "html", "javascript": "js"}
                    suffix = suffix_map.get(suffix, suffix)
                    print(f"P2WSH recommended file suffix: {suffix}")

                # Check if this would be misclassified
                if (
                    enhanced_results["original_magic"] == "application/octet-stream"
                    and enhanced_results["enhanced_detection"] != "application/octet-stream"
                ):
                    print("\n⚠️  P2WSH MISCLASSIFICATION DETECTED!")
                    print(f"   Magic detected: {enhanced_results['original_magic']}")
                    print(f"   Should be: {enhanced_results['enhanced_detection']}")

            except Exception as e:
                print(f"Failed to decode P2WSH data as base64: {e}")

            # Also try to analyze raw P2WSH data (not base64 encoded)
            try:
                print("\n--- P2WSH RAW DATA ANALYSIS ---")
                preview = p2wsh_data.decode("utf-8", errors="ignore")[:200]
                print(f"Raw P2WSH data preview: {repr(preview)}")

                # Original magic detection on raw data
                try:
                    original_mime = magic.from_buffer(p2wsh_data, mime=True)
                    print(f"Raw P2WSH original magic MIME: {original_mime}")
                except Exception as e:
                    original_mime = None
                    print(f"Raw P2WSH original magic failed: {e}")

                # Enhanced detection on raw data
                enhanced_results = enhanced_mime_detection(p2wsh_data, original_mime)

                print("\n--- P2WSH MIME DETECTION ANALYSIS (RAW DATA) ---")
                print(f"Original magic result: {enhanced_results['original_magic']}")
                print(f"Enhanced detection: {enhanced_results['enhanced_detection']}")
                print(f"Confidence: {enhanced_results['confidence']}")
                print(f"Reasons: {', '.join(enhanced_results['reasons'])}")

                # Determine file suffix
                if enhanced_results["enhanced_detection"]:
                    suffix = enhanced_results["enhanced_detection"].split("/")[-1]
                    # Apply suffix mapping
                    suffix_map = {"svg+xml": "svg", "plain": "txt", "xhtml+xml": "html", "javascript": "js"}
                    suffix = suffix_map.get(suffix, suffix)
                    print(f"Raw P2WSH recommended file suffix: {suffix}")

                # Check if this would be misclassified
                if (
                    enhanced_results["original_magic"] == "application/octet-stream"
                    and enhanced_results["enhanced_detection"] != "application/octet-stream"
                ):
                    print("\n⚠️  RAW P2WSH MISCLASSIFICATION DETECTED!")
                    print(f"   Magic detected: {enhanced_results['original_magic']}")
                    print(f"   Should be: {enhanced_results['enhanced_detection']}")

            except Exception:
                print(f"Raw P2WSH data (hex): {p2wsh_data[:50].hex()}")
        else:
            print("✗ No P2WSH stamp data found")

    if not found_stamp_data:
        print("\n⚠️  NO STAMP DATA FOUND IN ANY FORMAT")
        print("This transaction may not contain stamp data or uses an unsupported format")

    print("=" * 80 + "\n")


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Analyze MIME type detection for stamp transactions")
    parser.add_argument("--tx", type=str, help="Transaction hash to analyze", required=True)
    parser.add_argument(
        "--block", type=int, help="Block index (optional, will try to determine from transaction)", default=None
    )
    args = parser.parse_args()

    # Initialize API
    await setup_cp_api()

    # Fetch transaction details and raw transaction
    tx_info = await fetch_transaction_details(args.tx)
    tx_hex = await fetch_raw_transaction(args.tx)

    # Try to get block index from transaction info if not provided
    block_index = args.block
    if not block_index and tx_info:
        block_index = tx_info.get("block_index", 0)

    if tx_info:
        analyze_stamp_content(tx_info, args.tx, tx_hex, block_index or 0)
    else:
        print(f"Could not fetch transaction {args.tx}")


if __name__ == "__main__":
    asyncio.run(main())
