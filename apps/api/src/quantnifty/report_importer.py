from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

_HEADER = re.compile(
    rb"FILE : (?P<name>[^\r\n]+)\r\nPATH : (?P<path>[^\r\n]+)\r\n(?P<sep>=+)(?:\r\n|\n)"
)


def _inverse_cp1252() -> dict[int, int]:
    inverse: dict[int, int] = {}
    for value in range(256):
        try:
            char = bytes([value]).decode("cp1252")
            inverse[ord(char)] = value
        except UnicodeDecodeError:
            inverse[value] = value
    return inverse


_CP1252_INVERSE = _inverse_cp1252()


def _restore_exported_binary(content: bytes) -> bytes:
    """Restore Parquet bytes from the recorder's UTF-8/CP1252 text export.

    The affected recorder export converts binary CR (0x0d) characters into
    CRLF text line endings while also UTF-8 encoding CP1252 characters. For
    Parquet payloads those CR bytes can be part of Snappy-compressed data, so
    restoring CRLF to LF corrupts the compressed stream. Reverse the observed
    transformation with CRLF -> CR. Byte-preserving uploads remain supported
    when the payload is already valid Parquet.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    restored_text = text.replace("\r\n", "\r")
    try:
        candidate = bytes(_CP1252_INVERSE[ord(char)] for char in restored_text)
    except (KeyError, ValueError):
        return content
    if not _looks_like_parquet(candidate):
        return content
    return candidate


def _looks_like_parquet(data: bytes) -> bool:
    if len(data) < 12 or data[:4] != b"PAR1" or data[-4:] != b"PAR1":
        return False
    try:
        footer_len = int.from_bytes(data[-8:-4], "little", signed=False)
    except Exception:
        return False
    footer_start = len(data) - 8 - footer_len
    return footer_start >= 4 and footer_start < len(data) - 8 and data[footer_start] == 0x15


def extract_recorder_report(report: str | Path, destination: str | Path) -> int:
    """Extract recorder snapshot files from the textual data_Review export.

    The export is a concatenation of file headers and file bytes. Snapshot
    runtime JSON and Parquet files are materialized; unrelated files are ignored.
    """
    source = Path(report)
    target = Path(destination)
    data = source.read_bytes()
    target.mkdir(parents=True, exist_ok=True)
    matches = list(_HEADER.finditer(data))
    written = 0
    for index, match in enumerate(matches):
        name = match.group("name").decode("utf-8", "replace")
        original = match.group("path").decode("utf-8", "replace")
        if "\\data\\snapshots\\" not in original.lower():
            continue
        relative = Path(*original.replace("\\", "/").split("/data/snapshots/", 1)[1].split("/"))
        if name not in {"runtime.json", "option_chain.parquet", "greeks.parquet"}:
            continue
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(data)
        framed = data[content_start:content_end]
        separator = framed.rfind(b"\r\n======================================================================\r\nFILE :")
        if separator >= 0:
            framed = framed[:separator]
        elif framed.endswith(b"\r\n======================================================================\r\n"):
            framed = framed[:-len(b"\r\n======================================================================\r\n")]
        content = framed.rstrip(b"\r\n") if name.endswith(".parquet") else framed.strip(b"\r\n")
        if name.endswith(".parquet"):
            content = _restore_exported_binary(content)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        written += 1
    return written


def load_report_to_temporary_root(report: str | Path):
    """Return a TemporaryDirectory containing an extracted recorder tree."""
    temp = TemporaryDirectory(prefix="quantnifty-recording-")
    try:
        written = extract_recorder_report(report, temp.name)
        if written == 0:
            temp.cleanup()
            raise ValueError(f"no recorder snapshot files found in report: {report}")
        return temp
    except Exception:
        temp.cleanup()
        raise
