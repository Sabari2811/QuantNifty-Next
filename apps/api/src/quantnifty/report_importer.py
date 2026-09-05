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


def _decode_cp1252_utf8(text: str) -> bytes | None:
    try:
        return bytes(_CP1252_INVERSE[ord(char)] for char in text)
    except (KeyError, ValueError):
        return None


def _candidate_from_text(text: str, newline: str) -> bytes | None:
    if newline == "lf":
        text = text.replace("\r\n", "\n")
    elif newline == "cr":
        text = text.replace("\r\n", "\r")
    elif newline == "crlf":
        text = text.replace("\r\r\n", "\r\n")
    return _decode_cp1252_utf8(text)


def _repair_snappy_chunks(candidate: bytes) -> bytes:
    """Repair ambiguous CR/LF bytes inside Snappy column chunks.

    The recorder's text export can make an original binary CR or LF appear as
    CRLF. The Parquet footer remains readable, so use PyArrow metadata to find
    each column chunk and try the alternate LF->CR representation only for
    columns that are not readable as-is. This is deliberately constrained to
    chunk ranges; footer bytes and framing are never rewritten.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
    except ImportError:
        return candidate

    current = bytearray(candidate)
    try:
        reader = parquet.ParquetFile(pa.BufferReader(bytes(current)))
        metadata = reader.metadata
    except Exception:
        return candidate

    def column_name(column) -> str | None:
        value = getattr(column, "path_in_schema", None)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        return str(value).split(".")[-1]

    changed = False
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            name = column_name(column)
            start = getattr(column, "dictionary_page_offset", None)
            if start is None:
                start = column.data_page_offset
            end = column.data_page_offset + column.total_compressed_size
            if start is None or end is None or start < 0 or end <= start or end > len(current):
                continue
            chunk = bytes(current[start:end])
            if b"\n" not in chunk:
                continue

            original_ok = False
            try:
                parquet.read_table(pa.BufferReader(bytes(current)), columns=[name] if name else None)
                original_ok = True
            except Exception:
                pass
            if original_ok:
                continue

            repaired = chunk.replace(b"\n", b"\r")
            if repaired == chunk:
                continue
            trial = bytearray(current)
            trial[start:end] = repaired
            try:
                parquet.read_table(pa.BufferReader(bytes(trial)), columns=[name] if name else None)
            except Exception:
                continue
            current = trial
            changed = True

    if not changed:
        return candidate
    return bytes(current)


def _restore_exported_binary(content: bytes) -> bytes:
    """Restore Parquet bytes from the recorder's text export.

    First reconstruct the recorder's observed CR-based newline expansion. If
    that candidate is not readable, also try LF normalization. Finally repair
    individual unreadable Snappy column chunks where the export made LF/CR
    ambiguous. Validation is performed by PyArrow, not merely by PAR1/footer
    shape, so a structurally valid but Snappy-corrupt candidate is rejected.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    candidates: list[bytes] = []
    for newline in ("cr", "lf", "crlf"):
        candidate = _candidate_from_text(text, newline)
        if candidate is not None and candidate not in candidates and _looks_like_parquet(candidate):
            candidates.append(candidate)

    if not candidates:
        return content

    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet

        for candidate in candidates:
            try:
                parquet.read_table(pa.BufferReader(candidate))
                return candidate
            except Exception:
                repaired = _repair_snappy_chunks(candidate)
                if repaired != candidate:
                    try:
                        parquet.read_table(pa.BufferReader(repaired))
                        return repaired
                    except Exception:
                        pass
    except ImportError:
        pass

    # Preserve the recorder's historically observed representation when the
    # runtime cannot perform semantic Parquet validation.
    return candidates[0]


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
        separator = re.search(rb"(?:\r\n){1,3}={10,}\r\n(?:FILE :|$)", framed)
        if separator:
            framed = framed[:separator.start()]
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
