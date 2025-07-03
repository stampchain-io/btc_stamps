"""
Enhanced MIME type detection for Bitcoin Stamps
Provides improved detection for HTML, JavaScript, CSS and other content types
"""

import gzip

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


def is_svg_content(content_bytes):
    """
    Check if content is SVG by looking for SVG markers.

    Args:
        content_bytes (bytes): The content to analyze

    Returns:
        bool: True if content appears to be SVG
    """
    try:
        content_str = content_bytes.decode("utf-8", errors="ignore").lower()
        return "<svg" in content_str and ("xmlns" in content_str or "viewbox" in content_str)
    except Exception:
        return False


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

    # Try to detect gzipped content by magic number and MIME type
    try:
        magic_mime = magic.from_buffer(content_bytes, mime=True)
    except Exception:
        magic_mime = "application/octet-stream"

    # Check for gzip magic number (1f 8b) or gzip MIME types
    is_gzip_file = (
        content_bytes.startswith(b"\x1f\x8b")
        or magic_mime in ("application/gzip", "application/x-gzip")
        or magic_mime == "application/octet-stream"  # gzop files might be detected as octet-stream
    )

    if is_gzip_file:
        try:
            # Attempt to decompress
            decompressed = gzip.decompress(content_bytes)

            # Check if decompressed content is SVG
            if is_svg_content(decompressed):
                return decompressed, True, "image/svg+xml"
            else:
                # Return original content if decompressed content is not SVG
                return content_bytes, False, magic_mime

        except (gzip.BadGzipFile, OSError, EOFError, Exception):
            # Not actually gzipped or corrupted, return original
            return content_bytes, False, magic_mime

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
