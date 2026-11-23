"""Text decoding for exported reports."""


def decode_text(content: bytes) -> str:
    """Decode CSV bytes: UTF-8 (BOM tolerated), then UTF-16 (BOM required), then cp1252."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return content.decode("utf-16")
        except UnicodeDecodeError:
            pass
    return content.decode("cp1252", errors="replace")
