"""
Enhanced MIME type detection for Bitcoin Stamps
Provides improved detection for HTML, JavaScript, CSS and other content types
"""

import gzip
import zlib

import magic


def is_legitimate_html(content_bytes):
    """
    Enhanced HTML detection that excludes corrupted binary data.

    This function implements strict validation to ensure only legitimate HTML
    content is detected, preventing consensus-breaking changes from corrupted
    binary data that might contain HTML-like patterns.

    Args:
        content_bytes (bytes): The content to analyze

    Returns:
        bool: True if content is legitimate HTML, False otherwise
    """
    try:
        # Must be valid UTF-8
        content_str = content_bytes.decode("utf-8")

        # Must have low binary ratio (< 5%)
        binary_ratio = sum(1 for b in content_bytes if b < 32 and b not in [9, 10, 13]) / len(content_bytes)
        if binary_ratio > 0.05:
            return False

        # Must not have image headers
        if content_bytes.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8")):
            return False

        # Must have proper HTML structure
        content_lower = content_str.lower()
        has_html_tag = "<html" in content_lower
        has_body_tag = "<body" in content_lower

        if not (has_html_tag and has_body_tag):
            return False

        # Must be well-formed
        html_open = content_lower.count("<html")
        html_close = content_lower.count("</html>")
        body_open = content_lower.count("<body")
        body_close = content_lower.count("</body>")

        return html_open == html_close and body_open == body_close

    except UnicodeDecodeError:
        return False


def is_svg_content(content_bytes, max_check_size=512):
    """
    Check if content is SVG by looking for SVG markers.

    Performance optimization: Only decode first 512 bytes to check for SVG markers.

    Args:
        content_bytes (bytes): The content to analyze
        max_check_size (int): Maximum bytes to decode for SVG detection

    Returns:
        bool: True if content appears to be SVG
    """
    try:
        # Only decode a prefix for performance
        check_bytes = content_bytes[:max_check_size]
        content_str = check_bytes.decode("utf-8", errors="ignore").lower()
        return "<svg" in content_str and ("xmlns" in content_str or "viewbox" in content_str)
    except Exception:
        return False


def is_gzip(content_bytes):
    """
    Check if content appears to be gzipped.

    Args:
        content_bytes (bytes): The content to check

    Returns:
        bool: True if content appears to be gzipped
    """
    return len(content_bytes) >= 3 and content_bytes[:2] == b"\x1f\x8b" and content_bytes[2] == 0x08


def try_decompress(content_bytes):
    """
    Attempt to decompress gzipped content.

    Args:
        content_bytes (bytes): The gzipped content

    Returns:
        bytes or None: Decompressed content if successful, None otherwise
    """
    try:
        return gzip.decompress(content_bytes)
    except (gzip.BadGzipFile, OSError, EOFError, zlib.error):
        return None


def detect_and_decompress_svg(content_bytes):
    """
    Detect and decompress gzipped SVG files (svgz) or gzipped binary files containing SVG.

    Args:
        content_bytes (bytes): The content to analyze and potentially decompress

    Returns:
        tuple: (decompressed_content_bytes, is_svg, mime_type)
               - decompressed_content_bytes: Original or decompressed content
               - is_svg: True if content is SVG after decompression
               - mime_type: Detected MIME type ("image/svg+xml" for SVG)
    """
    # Check if content is already SVG
    if is_svg_content(content_bytes):
        return content_bytes, True, "image/svg+xml"

    # Performance optimization: Check gzip header first before calling magic
    if is_gzip(content_bytes):
        decompressed = try_decompress(content_bytes)
        if decompressed and is_svg_content(decompressed):
            return decompressed, True, "image/svg+xml"

    # If not obviously gzipped, check with magic for edge cases
    try:
        magic_mime = magic.from_buffer(content_bytes, mime=True)
    except Exception:
        magic_mime = "application/octet-stream"

    # Check for gzip MIME types that weren't caught by header check
    if magic_mime in ("application/gzip", "application/x-gzip"):
        decompressed = try_decompress(content_bytes)
        if decompressed and is_svg_content(decompressed):
            return decompressed, True, "image/svg+xml"

    # Not gzipped or not SVG after decompression
    return content_bytes, False, magic_mime


def get_processed_content_and_mime(content_bytes):
    """
    Get both processed content and MIME type for content that may need decompression.

    Args:
        content_bytes (bytes): The content to analyze

    Returns:
        tuple: (processed_content_bytes, mime_type)
               - processed_content_bytes: Original or decompressed content
               - mime_type: The detected MIME type
    """
    # Check for gzipped SVG files first
    processed_content, is_svg, svg_mime = detect_and_decompress_svg(content_bytes)
    if is_svg:
        return processed_content, svg_mime

    # Use processed content for further detection
    content_to_analyze = processed_content

    # Try standard magic detection
    try:
        magic_mime = magic.from_buffer(content_to_analyze, mime=True)
    except Exception:
        magic_mime = "application/octet-stream"

    # Enhanced detection for specific types
    if is_legitimate_html(content_to_analyze):
        return content_to_analyze, "text/html"

    # For other types, fall back to magic detection
    return content_to_analyze, magic_mime


def enhanced_mime_detection(content_bytes):
    """
    Enhanced MIME type detection with custom logic for better accuracy.

    This function provides improved MIME detection that can identify content
    types that python-magic might miss or misclassify, particularly for
    HTML, JavaScript, CSS content, and gzipped SVG files.

    Args:
        content_bytes (bytes): The content to analyze

    Returns:
        str: The detected MIME type
    """
    _, mime_type = get_processed_content_and_mime(content_bytes)
    return mime_type
