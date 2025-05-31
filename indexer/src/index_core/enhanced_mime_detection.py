"""
Enhanced MIME type detection for Bitcoin Stamps
Provides improved detection for HTML, JavaScript, CSS and other content types
"""

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
        content_str = content_bytes.decode('utf-8')
        
        # Must have low binary ratio (< 5%)
        binary_ratio = sum(1 for b in content_bytes if b < 32 and b not in [9, 10, 13]) / len(content_bytes)
        if binary_ratio > 0.05:
            return False
            
        # Must not have image headers
        if content_bytes.startswith((b'\x89PNG', b'\xff\xd8\xff', b'GIF8')):
            return False
            
        # Must have proper HTML structure
        content_lower = content_str.lower()
        has_html_tag = '<html' in content_lower
        has_body_tag = '<body' in content_lower
        
        if not (has_html_tag and has_body_tag):
            return False
            
        # Must be well-formed
        html_open = content_lower.count('<html')
        html_close = content_lower.count('</html>')
        body_open = content_lower.count('<body')
        body_close = content_lower.count('</body>')
        
        return html_open == html_close and body_open == body_close
        
    except UnicodeDecodeError:
        return False


def enhanced_mime_detection(content_bytes):
    """
    Enhanced MIME type detection with custom logic for better accuracy.
    
    This function provides improved MIME detection that can identify content
    types that python-magic might miss or misclassify, particularly for
    HTML, JavaScript, and CSS content.
    
    Args:
        content_bytes (bytes): The content to analyze
        
    Returns:
        str: The detected MIME type
    """
    # Try standard magic detection first
    try:
        magic_mime = magic.from_buffer(content_bytes, mime=True)
    except Exception:
        magic_mime = 'application/octet-stream'
    
    # Enhanced detection for specific types
    if is_legitimate_html(content_bytes):
        return 'text/html'
    
    # For other types, fall back to magic detection
    # Future enhancements can add JavaScript, CSS, etc. detection here
    
    return magic_mime 