import json

import pyarrow as pa
import pyarrow.parquet as pq

from quantnifty.recording_loader import load_recording
from quantnifty.report_importer import extract_recorder_report


SEP = b"=" * 70


def _section(name: str, path: str, payload: bytes) -> bytes:
    return b"FILE : " + name.encode() + b"\r\nPATH : " + path.encode() + b"\r\n" + SEP + b"\r\n" + payload + b"\r\n"


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
    # The affected recorder export expands binary CR characters to CRLF before
    # UTF-8 encoding. Do not normalize CR to LF: CR bytes occur inside Snappy.
    return "".join(chars).replace("\r", "\r\n").encode("utf-8")


def test_report_importer_restores_utf8_transcoded_binary(tmp_path):
    option = tmp_path / "option_chain.parquet"
    pq.write_table(pa.Table.from_pylist([{
        "Strike": 24400, "CE_ID": 1, "CE_LTP": 100.0, "CE_OI": 1000,
        "CE_VOLUME": 5000, "PE_ID": 2, "PE_LTP": 120.0, "PE_OI": 1100,
        "PE_VOLUME": 5100,
    }]), option)
    report = tmp_path / "data_Review.txt"
    base = r"D:\Projects\NiftySignalEngine\data\snapshots\04-Aug-2026\000001_13-02-21"
    report.write_bytes(_section("option_chain.parquet", base + r"\option_chain.parquet", _transcode_binary_for_export(option.read_bytes())))
    extracted = tmp_path / "restored"
    assert extract_recorder_report(report, extracted) == 1
    assert (extracted / "04-Aug-2026" / "000001_13-02-21" / "option_chain.parquet").read_bytes() == option.read_bytes()
