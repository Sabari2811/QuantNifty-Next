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


def _parquet_footer_start(data: bytes) -> int | None:
    if len(data) < 12 or data[:4] != b"PAR1" or data[-4:] != b"PAR1":
        return None
    footer_len = int.from_bytes(data[-8:-4], "little", signed=False)
    start = len(data) - 8 - footer_len
    if start < 4 or start >= len(data) - 8:
        return None
    return start


def _hybrid_data_candidate(lf_candidate: bytes, cr_candidate: bytes) -> bytes | None:
    """Use LF reconstruction for footer metadata and CR for binary pages."""
    if len(lf_candidate) != len(cr_candidate):
        return None
    footer_start = _parquet_footer_start(lf_candidate)
    if footer_start is None or _parquet_footer_start(cr_candidate) != footer_start:
        return None
    return cr_candidate[:footer_start] + lf_candidate[footer_start:]


def _restore_exported_binary(content: bytes) -> bytes:
    """Restore Parquet bytes from the recorder's text export.

    The export can make binary CR bytes appear as LF while the Parquet footer
    can contain genuine LF bytes. Therefore test both reconstructions and then
    combine CR-based data pages with the LF-based footer when needed.
    """
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

        # Prefer a directly readable reconstruction.
        for newline in ("lf", "cr", "crlf"):
            candidate = candidates.get(newline)
            if candidate is None:
                continue
            try:
                parquet.read_table(pa.BufferReader(candidate))
                return candidate
            except Exception:
                pass

        # Known recorder failure mode: LF footer + CR data pages.
        lf_candidate = candidates.get("lf")
        cr_candidate = candidates.get("cr")
        if lf_candidate is not None and cr_candidate is not None:
            hybrid = _hybrid_data_candidate(lf_candidate, cr_candidate)
            if hybrid is not None:
                try:
                    parquet.read_table(pa.BufferReader(hybrid))
                    return hybrid
                except Exception:
                    pass
    except ImportError:
        pass

    return candidates.get("lf") or candidates.get("cr") or candidates["crlf"]


def _looks_like_parquet(data: bytes) -> bool:
    return _parquet_footer_start(data) is not None


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
