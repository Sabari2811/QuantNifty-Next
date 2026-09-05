import json

import pyarrow as pa
import pyarrow.parquet as pq

from quantnifty.recording_loader import load_recording
from quantnifty.report_importer import (
    _column_metadata_entries,
    _parquet_footer_start,
    _parse_thrift_struct,
    _serialize_thrift_struct,
    _set_field,
    _repair_footer_and_get_chunks,
    extract_recorder_report,
)


SEP = b"=" * 70
FRAME = b"\r\n" + SEP + b"\r\n"


def _section(name: str, path: str, payload: bytes) -> bytes:
    return b"FILE : " + name.encode() + b"\r\nPATH : " + path.encode() + b"\r\n" + SEP + b"\r\n" + payload + b"\r\n" + FRAME


def test_report_importer_preserves_parquet_and_json(tmp_path):
    option = tmp_path / "option_chain.parquet"
    greeks = tmp_path / "greeks.parquet"
    pq.write_table(pa.Table.from_pylist([{
        "Strike": 24400, "CE_ID": 1, "CE_LTP": 100.0, "CE_OI": 1000,
        "CE_VOLUME": 5000, "PE_ID": 2, "PE_LTP": 120.0, "PE_OI": 1100,
        "PE_VOLUME": 5100,
    }]), option)
    pq.write_table(pa.Table.from_pylist([{
        "Strike": 24400, "CE_IV": 0.10, "CE_DELTA": 0.48, "CE_GAMMA": 0.02,
        "CE_THETA": -0.01, "CE_VEGA": 0.03, "PE_IV": 0.11, "PE_DELTA": -0.52,
        "PE_GAMMA": 0.02, "PE_THETA": -0.01, "PE_VEGA": 0.03,
    }]), greeks)
    runtime = json.dumps({
        "timestamp": "04-Aug-2026 13:02:21", "spot": 24383.6,
        "symbol": "NIFTY", "expiry": "08/04/2026 14:00",
        "regime": "RANGE", "runtime_status": "RUNNING",
    }).encode()
    report = tmp_path / "data_Review.txt"
    base = r"D:\Projects\NiftySignalEngine\data\snapshots\04-Aug-2026\000001_13-02-21"
    report.write_bytes(
        _section("runtime.json", base + r"\runtime.json", runtime)
        + _section("option_chain.parquet", base + r"\option_chain.parquet", option.read_bytes())
        + _section("greeks.parquet", base + r"\greeks.parquet", greeks.read_bytes())
    )

    extracted = tmp_path / "extracted"
    assert extract_recorder_report(report, extracted) == 3
    assert (extracted / "04-Aug-2026" / "000001_13-02-21" / "option_chain.parquet").read_bytes() == option.read_bytes()

    snapshots = load_recording(report)
    assert len(snapshots) == 1
    assert snapshots[0]["data_integrity"] == "RECORDED_HISTORICAL"
    assert {row["side"] for row in snapshots[0]["option_chain"]} == {"CE", "PE"}


def _transcode_binary_for_export(payload: bytes) -> bytes:
    chars = []
    for value in payload:
        try:
            chars.append(bytes([value]).decode("cp1252"))
        except UnicodeDecodeError:
            chars.append(chr(value))
    return "".join(chars).replace("\r", "\r\n").encode("utf-8")


def test_report_importer_restores_utf8_transcoded_binary_and_strips_frame(tmp_path):
    option = tmp_path / "option_chain.parquet"
    original = pa.Table.from_pylist([{
        "Strike": 24400, "CE_ID": 1, "CE_LTP": 100.0, "CE_OI": 1000,
        "CE_VOLUME": 5000, "PE_ID": 2, "PE_LTP": 120.0, "PE_OI": 1100,
        "PE_VOLUME": 5100,
    }])
    pq.write_table(original, option)
    report = tmp_path / "data_Review.txt"
    base = r"D:\Projects\NiftySignalEngine\data\snapshots\04-Aug-2026\000001_13-02-21"
    report.write_bytes(
        _section("option_chain.parquet", base + r"\option_chain.parquet", _transcode_binary_for_export(option.read_bytes()))
        + _section("runtime.json", base + r"\runtime.json", b"{}")
    )
    extracted = tmp_path / "restored"
    assert extract_recorder_report(report, extracted) == 2
    restored = extracted / "04-Aug-2026" / "000001_13-02-21" / "option_chain.parquet"
    assert pq.read_table(restored).equals(original)


def test_footer_offset_recovery_uses_page_structure(tmp_path):
    option = tmp_path / "option_chain.parquet"
    original = pa.Table.from_pylist([{
        "Strike": 24400, "CE_ID": 1, "CE_LTP": 100.0, "CE_OI": 1000,
        "CE_VOLUME": 5000, "PE_ID": 2, "PE_LTP": 120.0, "PE_OI": 1100,
        "PE_VOLUME": 5100,
    }])
    pq.write_table(original, option)
    raw = option.read_bytes()
    footer_start = _parquet_footer_start(raw)
    assert footer_start is not None

    footer = _parse_thrift_struct(raw[footer_start:-8])
    first_column = _column_metadata_entries(footer)[0]
    _set_field(first_column, 11, 0)
    corrupted_footer = _serialize_thrift_struct(footer)
    corrupted = raw[:footer_start] + corrupted_footer + len(corrupted_footer).to_bytes(4, "little") + b"PAR1"

    rebuilt, chunks = _repair_footer_and_get_chunks(corrupted, raw)
    assert chunks
    restored = tmp_path / "restored.parquet"
    restored.write_bytes(rebuilt)
    assert pq.read_table(restored).equals(original)
