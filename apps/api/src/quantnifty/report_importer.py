from __future__ import annotations

import itertools
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


def _parquet_footer_start(data: bytes) -> int | None:
    if len(data) < 12 or data[:4] != b"PAR1" or data[-4:] != b"PAR1":
        return None
    footer_len = int.from_bytes(data[-8:-4], "little", signed=False)
    start = len(data) - 8 - footer_len
    if start < 4 or start >= len(data) - 8:
        return None
    return start


def _looks_like_parquet(data: bytes) -> bool:
    return _parquet_footer_start(data) is not None


def _column_chunk_bounds(metadata) -> list[tuple[str, int, int]]:
    bounds: list[tuple[str, int, int]] = []
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            name = getattr(column, "path_in_schema", None)
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            name = str(name or "").split(".")[-1]
            start = getattr(column, "dictionary_page_offset", None)
            if start is None:
                start = column.data_page_offset
            end = column.data_page_offset + column.total_compressed_size
            if start is None or end is None or start < 0 or end <= start:
                continue
            bounds.append((name, int(start), int(end)))
    return bounds


def _readable(parquet, pa, candidate: bytes, column: str | None = None) -> bool:
    try:
        table = parquet.read_table(pa.BufferReader(candidate), columns=[column] if column else None)
        return table.num_rows >= 0
    except Exception:
        return False


def _repair_mixed_newlines(lf_candidate: bytes, cr_candidate: bytes) -> bytes | None:
    """Repair ambiguous CR/LF bytes independently inside each column chunk.

    The recorder export loses whether an original binary 0x0A or 0x0D produced
    a CRLF sequence. A whole-file newline choice is therefore unsafe. The LF
    candidate supplies the readable footer metadata; the CR candidate supplies
    the generally valid Snappy page bytes. For each column that still fails,
    search only its ambiguous bytes and accept the first semantically readable
    reconstruction. Chunk-local search keeps the ambiguity bounded (the
    supplied recordings have at most a small number of ambiguous bytes per
    column chunk) and avoids modifying unrelated footer bytes.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
    except ImportError:
        return None

    footer_start = _parquet_footer_start(lf_candidate)
    if footer_start is None or _parquet_footer_start(cr_candidate) != footer_start:
        return None
    try:
        metadata = parquet.ParquetFile(pa.BufferReader(lf_candidate)).metadata
    except Exception:
        return None

    current = bytearray(cr_candidate[:footer_start] + lf_candidate[footer_start:])
    for name, start, end in _column_chunk_bounds(metadata):
        ambiguous = [offset for offset in range(start, end) if lf_candidate[offset] != cr_candidate[offset]]
        if not ambiguous or _readable(parquet, pa, bytes(current), name):
            continue

        found = None
        for count in range(1, len(ambiguous) + 1):
            for indexes in itertools.combinations(range(len(ambiguous)), count):
                trial = bytearray(current)
                for index in indexes:
                    offset = ambiguous[index]
                    trial[offset] = lf_candidate[offset]
                if _readable(parquet, pa, bytes(trial), name):
                    found = trial
                    break
            if found is not None:
                break
        if found is None:
            raise ValueError(
                f"unable to reconstruct Parquet column chunk {name} "
                f"({len(ambiguous)} ambiguous newline bytes)"
            )
        current = found

    result = bytes(current)
    if _readable(parquet, pa, result):
        return result
    return None


def _restore_exported_binary(content: bytes) -> bytes:
    """Restore Parquet bytes from a recorder text export."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    candidates: dict[str, bytes] = {}
    for newline in ("lf", "cr", "crlf"):
        candidate = _candidate_from_text(text, newline)
        if candidate is not None and _looks_like_parquet(candidate):
            candidates[newline] = candidate

    if not candidates:
        return content

    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
        for newline in ("lf", "cr", "crlf"):
            candidate = candidates.get(newline)
            if candidate is not None and _readable(parquet, pa, candidate):
                return candidate

        lf_candidate = candidates.get("lf")
        cr_candidate = candidates.get("cr")
        if lf_candidate is not None and cr_candidate is not None:
            repaired = _repair_mixed_newlines(lf_candidate, cr_candidate)
            if repaired is not None:
                return repaired
    except ImportError:
        pass

    return candidates.get("cr") or candidates.get("lf") or candidates["crlf"]


def extract_recorder_report(report: str | Path, destination: str | Path) -> int:
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
