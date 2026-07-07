# CONSENSUS-CRITICAL: the base64 alphabet -> 6-bit-value lookup table used by
# ``lenient_b64decode``. Index by the ASCII byte value; -1 means "not a base64
# alphabet character" (skipped in lenient mode, exactly like the historical
# CPython 3.10 ``binascii.a2b_base64`` non-strict decoder).
_B64_ALPHABET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_A2B_TABLE = [-1] * 256
for _idx, _ch in enumerate(_B64_ALPHABET):
    _B64_A2B_TABLE[_ch] = _idx
_B64_PAD = ord("=")


class LenientBase64Error(ValueError):
    """Raised by ``lenient_b64decode`` for inputs the historical (3.10) decoder rejected."""


def lenient_b64decode(base64_input):
    """Decode base64 EXACTLY as CPython 3.10's ``base64.b64decode`` did — on every interpreter.

    CONSENSUS-CRITICAL. This is a faithful, version-independent reimplementation
    of ``binascii.a2b_base64`` in *non-strict* mode as shipped in CPython 3.10
    (the runtime production/consensus was certified on). Python 3.13 tightened
    ``binascii.a2b_base64`` so it rejects non-canonical base64 (embedded ``=``
    padding, stray non-alphabet chars, "N data characters cannot be 1 more than
    a multiple of 4") that 3.10-3.12 decoded leniently. That strictness caused a
    consensus divergence at block 783775 (see #871): a stamp payload whose base64
    contains embedded padding decoded to a 373-byte PNG on 3.10-3.12 but raised
    on 3.13, mis-classifying the stamp as cursed/UNKNOWN and forking ``txlist_hash``.

    Routing all stamp decoding through this single deterministic decoder makes the
    result identical on 3.10, 3.11, 3.12 and 3.13 (and any future interpreter),
    with **no per-version branching and no monkey-patching**. It is proven
    byte-identical to 3.10 ``base64.b64decode`` across an 85k-input fuzz corpus
    (canonical, embedded-pad, non-alphabet and non-ASCII inputs) plus the real
    block-783775 payload — see ``tests/test_python313_base64_regression.py``.

    Semantics (matching CPython 3.10 non-strict a2b_base64):
      * characters outside the standard base64 alphabet are skipped;
      * a ``=`` that completes a quantum (seen once >= 2 alphabet chars into the
        current group) terminates decoding — trailing bytes after it are ignored;
      * a dangling single alphabet char (``quad_pos == 1``) at end-of-input
        raises (the "cannot be 1 more than a multiple of 4" case);
      * a group left with 2-3 chars and no padding raises "Incorrect padding".

    Args:
        base64_input (str | bytes | bytearray): the base64 data to decode.

    Returns:
        bytes: the decoded bytes.

    Raises:
        LenientBase64Error / ValueError: for inputs 3.10 also rejected.
    """
    if isinstance(base64_input, str):
        # base64.b64decode encodes str via ASCII and rejects non-ASCII; mirror that.
        data = base64_input.encode("ascii")
    else:
        data = bytes(base64_input)

    out = bytearray()
    table = _B64_A2B_TABLE
    quad_pos = 0
    leftchar = 0
    pads = 0
    for ch in data:
        if ch == _B64_PAD:
            pads += 1
            if quad_pos >= 2 and quad_pos + pads >= 4:
                # Valid padding completes the quantum: stop (non-strict 3.10 behavior).
                return bytes(out)
            continue
        value = table[ch]
        if value == -1:
            # Non-alphabet character: skipped in non-strict mode.
            continue
        pads = 0
        if quad_pos == 0:
            quad_pos = 1
            leftchar = value
        elif quad_pos == 1:
            quad_pos = 2
            out.append(((leftchar << 2) | (value >> 4)) & 0xFF)
            leftchar = value & 0x0F
        elif quad_pos == 2:
            quad_pos = 3
            out.append(((leftchar << 4) | (value >> 2)) & 0xFF)
            leftchar = value & 0x03
        else:  # quad_pos == 3
            quad_pos = 0
            out.append(((leftchar << 6) | value) & 0xFF)
            leftchar = 0

    if quad_pos != 0:
        if quad_pos == 1:
            raise LenientBase64Error(
                "Invalid base64-encoded string: number of data characters (%d) "
                "cannot be 1 more than a multiple of 4" % (len(out) // 3 * 4 + 1)
            )
        raise LenientBase64Error("Incorrect padding")
    return bytes(out)


def parse_base64_from_description(description):
    """
    Parse base64 data and mimetype from a description string.

    Args:
        description (str): The description string to parse.

    Returns:
        tuple: (base64_string, mimetype) or (None, None) if no stamp data found.
    """
    if description is not None and description.lower().find("stamp:") != -1:
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
