def parse_base64_from_description(description):
    """
    Parse base64 data and mimetype from a description string.

    Args:
        description (str): The description string to parse.

    Returns:
        tuple: (base64_string, mimetype) or (None, None) if no stamp data found.
    """
    if description is not None and description.lower().find("stamp:") != -1:
        # Check if this is a stamp:721 pattern (NOT base64 data)
        if description.lower().startswith("stamp:721"):
            # This is a protocol identifier, not base64 data
            return None, None
            
        stamp_search = description[description.lower().find("stamp:") + 6 :]
        stamp_search = stamp_search.strip()
        if ";" in stamp_search:
            stamp_mimetype, stamp_base64 = stamp_search.split(";", 1)
            stamp_mimetype = stamp_mimetype.strip() if len(stamp_mimetype) <= 255 else ""  # db limit
            stamp_base64 = stamp_base64.strip() if len(stamp_base64) > 1 else None
        else:
            stamp_mimetype = ""
            stamp_base64 = stamp_search.strip() if len(stamp_search) > 1 else None

        return stamp_base64, stamp_mimetype
    else:
        return None, None
