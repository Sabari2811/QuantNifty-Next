from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

_HEADER = re.compile(
    rb"FILE : (?P<name>[^\r\n]+)\r\nPATH : (?P<path>[^\r\n]+)\r\n(?P<sep>=+)(?:\r\n|\n)"
)
_NEXT = b"\r\n======================================================================\r\nFILE :"


def extract_recorder_report(report: str | Path, destination: str | Path) -> int:
    """Extract recorder snapshot files from the textual data_Review export.

    The export is a concatenation of file headers and raw file bytes. Only
    snapshot runtime JSON and Parquet files are materialized; unrelated files
    from the report are deliberately ignored.
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
        # A report section is terminated by the separator immediately before
        # the next FILE header. Remove that framing, but preserve raw bytes.
        framed = data[content_start:content_end]
        if framed.endswith(_NEXT[len(b"\r\n======================================================================\r\nFILE :"):]):
            pass
        separator = framed.rfind(b"\r\n======================================================================\r\nFILE :")
        if separator >= 0:
            framed = framed[:separator]
        elif framed.endswith(b"\r\n======================================================================\r\n"):
            framed = framed[:-len(b"\r\n======================================================================\r\n")]
        content = framed.rstrip(b"\r\n") if name.endswith(".parquet") else framed.strip(b"\r\n")
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
