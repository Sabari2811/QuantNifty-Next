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


def _readable(parquet, pa, candidate: bytes, column: str | None = None) -> bool:
    try:
        table = parquet.read_table(pa.BufferReader(candidate), columns=[column] if column else None)
        return table.num_rows >= 0
    except Exception:
        return False


def _thrift_skip(protocol, thrift_type: int) -> None:
    """Skip a compact-protocol value while preserving unknown Parquet metadata."""
    from thrift.Thrift import TType

    if thrift_type == TType.BOOL:
        protocol.readBool()
    elif thrift_type == TType.BYTE:
        protocol.readByte()
    elif thrift_type == TType.I16:
        protocol.readI16()
    elif thrift_type == TType.I32:
        protocol.readI32()
    elif thrift_type == TType.I64:
        protocol.readI64()
    elif thrift_type == TType.DOUBLE:
        protocol.readDouble()
    elif thrift_type == TType.STRING:
        protocol.readBinary()
    elif thrift_type == TType.STRUCT:
        protocol.readStructBegin()
        while True:
            _, field_type, _ = protocol.readFieldBegin()
            if field_type == TType.STOP:
                break
            _thrift_skip(protocol, field_type)
            protocol.readFieldEnd()
        protocol.readStructEnd()
    elif thrift_type in (TType.LIST, TType.SET):
        if thrift_type == TType.LIST:
            element_type, count = protocol.readListBegin()
        else:
            element_type, count = protocol.readSetBegin()
        for _ in range(count):
            _thrift_skip(protocol, element_type)
        if thrift_type == TType.LIST:
            protocol.readListEnd()
        else:
            protocol.readSetEnd()
    elif thrift_type == TType.MAP:
        key_type, value_type, count = protocol.readMapBegin()
        for _ in range(count):
            _thrift_skip(protocol, key_type)
            _thrift_skip(protocol, value_type)
        protocol.readMapEnd()


def _parse_thrift_struct(data: bytes):
    from thrift.Thrift import TType
    from thrift.protocol import TCompactProtocol
    from thrift.transport import TTransport

    protocol = TCompactProtocol.TCompactProtocol(TTransport.TMemoryBuffer(data))

    def read_value(thrift_type: int):
        if thrift_type == TType.BOOL:
            return protocol.readBool()
        if thrift_type == TType.BYTE:
            return protocol.readByte()
        if thrift_type == TType.I16:
            return protocol.readI16()
        if thrift_type == TType.I32:
            return protocol.readI32()
        if thrift_type == TType.I64:
            return protocol.readI64()
        if thrift_type == TType.DOUBLE:
            return protocol.readDouble()
        if thrift_type == TType.STRING:
            return protocol.readBinary()
        if thrift_type == TType.STRUCT:
            protocol.readStructBegin()
            fields = []
            while True:
                _, field_type, field_id = protocol.readFieldBegin()
                if field_type == TType.STOP:
                    break
                fields.append((field_id, field_type, read_value(field_type)))
                protocol.readFieldEnd()
            protocol.readStructEnd()
            return fields
        if thrift_type in (TType.LIST, TType.SET):
            if thrift_type == TType.LIST:
                element_type, count = protocol.readListBegin()
            else:
                element_type, count = protocol.readSetBegin()
            values = [read_value(element_type) for _ in range(count)]
            if thrift_type == TType.LIST:
                protocol.readListEnd()
            else:
                protocol.readSetEnd()
            return (element_type, values)
        if thrift_type == TType.MAP:
            key_type, value_type = protocol.readMapBegin()[:2]
            protocol.cstringio_buf.seek(protocol.cstringio_buf.tell())
            raise ValueError("Parquet footer map fields are not supported for reconstruction")
        raise ValueError(f"unsupported Thrift type: {thrift_type}")

    return read_value(TType.STRUCT)


def _serialize_thrift_struct(value) -> bytes:
    from thrift.protocol import TCompactProtocol
    from thrift.Thrift import TType
    from thrift.transport import TTransport

    transport = TTransport.TMemoryBuffer()
    protocol = TCompactProtocol.TCompactProtocol(transport)

    def write_value(thrift_type: int, item) -> None:
        if thrift_type == TType.BOOL:
            protocol.writeBool(item)
        elif thrift_type == TType.BYTE:
            protocol.writeByte(item)
        elif thrift_type == TType.I16:
            protocol.writeI16(item)
        elif thrift_type == TType.I32:
            protocol.writeI32(item)
        elif thrift_type == TType.I64:
            protocol.writeI64(item)
        elif thrift_type == TType.DOUBLE:
            protocol.writeDouble(item)
        elif thrift_type == TType.STRING:
            protocol.writeBinary(item)
        elif thrift_type == TType.STRUCT:
            protocol.writeStructBegin("")
            for field_id, field_type, field_value in item:
                protocol.writeFieldBegin("", field_type, field_id)
                write_value(field_type, field_value)
                protocol.writeFieldEnd()
            protocol.writeFieldStop()
            protocol.writeStructEnd()
        elif thrift_type in (TType.LIST, TType.SET):
            element_type, values = item
            if thrift_type == TType.LIST:
                protocol.writeListBegin(element_type, len(values))
            else:
                protocol.writeSetBegin(element_type, len(values))
            for field_value in values:
                write_value(element_type, field_value)
            if thrift_type == TType.LIST:
                protocol.writeListEnd()
            else:
                protocol.writeSetEnd()
        elif thrift_type == TType.MAP:
            key_type, value_type, values = item
            protocol.writeMapBegin(key_type, value_type, len(values))
            for key, field_value in values:
                write_value(key_type, key)
                write_value(value_type, field_value)
            protocol.writeMapEnd()
        else:
            raise ValueError(f"unsupported Thrift type: {thrift_type}")

    write_value(TType.STRUCT, value)
    return transport.getvalue()


def _column_metadata_entries(metadata_struct):
    """Yield mutable ColumnMetaData field lists from FileMetaData."""
    from thrift.Thrift import TType

    row_groups_field = next(
        (value for field_id, field_type, value in metadata_struct if field_id == 4 and field_type == TType.LIST),
        None,
    )
    if row_groups_field is None:
        return []
    _, groups = row_groups_field
    entries = []
    for row_group in groups:
        columns_field = next(
            (value for field_id, field_type, value in row_group if field_id == 1 and field_type == TType.LIST),
            None,
        )
        if columns_field is None:
            continue
        _, columns = columns_field
        for column_chunk in columns:
            metadata_field = next(
                (value for field_id, field_type, value in column_chunk if field_id == 3 and field_type == TType.STRUCT),
                None,
            )
            if metadata_field is not None:
                entries.append(metadata_field)
    return entries


def _field_value(fields, field_id):
    for index, (fid, thrift_type, value) in enumerate(fields):
        if fid == field_id:
            return index, thrift_type, value
    return None


def _set_field(fields, field_id, value, thrift_type=None) -> None:
    found = _field_value(fields, field_id)
    if found is None:
        if thrift_type is None:
            from thrift.Thrift import TType
            thrift_type = TType.I64
        fields.append((field_id, thrift_type, value))
    else:
        index, existing_type, _ = found
        fields[index] = (field_id, thrift_type or existing_type, value)


def _scan_parquet_pages(data: bytes, footer_start: int):
    """Scan page headers from the data area without trusting corrupted footer offsets."""
    from thrift.protocol import TCompactProtocol
    from thrift.transport import TTransport
    from thrift.Thrift import TType

    pages = []
    position = 4
    while position < footer_start:
        transport = TTransport.TMemoryBuffer(data[position:footer_start])
        protocol = TCompactProtocol.TCompactProtocol(transport)
        protocol.readStructBegin()
        header = {}
        data_page = None
        while True:
            _, field_type, field_id = protocol.readFieldBegin()
            if field_type == TType.STOP:
                break
            if field_id in (1, 2, 3, 4) and field_type == TType.I32:
                header[field_id] = protocol.readI32()
            elif field_id == 5 and field_type == TType.STRUCT:
                protocol.readStructBegin()
                data_page = {}
                while True:
                    _, nested_type, nested_id = protocol.readFieldBegin()
                    if nested_type == TType.STOP:
                        break
                    if nested_type == TType.I32:
                        data_page[nested_id] = protocol.readI32()
                    else:
                        _thrift_skip(protocol, nested_type)
                    protocol.readFieldEnd()
                protocol.readStructEnd()
            else:
                _thrift_skip(protocol, field_type)
            protocol.readFieldEnd()
        protocol.readStructEnd()
        header_length = transport.cstringio_buf.tell()
        compressed_size = int(header.get(3, 0))
        if header_length <= 0 or compressed_size < 0 or position + header_length + compressed_size > footer_start:
            raise ValueError(f"invalid Parquet page header at byte offset {position}")
        pages.append({
            "start": position,
            "header_length": header_length,
            "end": position + header_length + compressed_size,
            "type": int(header.get(1, -1)),
            "uncompressed_size": int(header.get(2, 0)),
            "compressed_size": compressed_size,
            "data_page": data_page,
        })
        position = pages[-1]["end"]
    if position != footer_start:
        raise ValueError(f"Parquet page scan ended at {position}, expected footer at {footer_start}")
    return pages


def _repair_footer_and_get_chunks(lf_candidate: bytes, cr_candidate: bytes):
    """Repair corrupted footer offsets using page structure, then return the file."""
    from thrift.Thrift import TType

    footer_start = _parquet_footer_start(lf_candidate)
    if footer_start is None or _parquet_footer_start(cr_candidate) != footer_start:
        return None, None

    pages = _scan_parquet_pages(cr_candidate, footer_start)
    metadata = _parse_thrift_struct(lf_candidate[footer_start:-8])
    column_entries = _column_metadata_entries(metadata)
    if not column_entries:
        return None, None

    # The recorder snapshots currently contain one dictionary page followed by
    # one data page per column. Refuse to guess if that on-disk contract changes.
    if len(pages) != len(column_entries) * 2:
        raise ValueError(
            f"unsupported recorder Parquet layout: {len(pages)} pages for "
            f"{len(column_entries)} columns; expected exactly two pages per column"
        )

    chunk_info = []
    for index, column_meta in enumerate(column_entries):
        dictionary_page, data_page = pages[index * 2:index * 2 + 2]
        if dictionary_page["type"] != 2 or data_page["type"] != 0:
            raise ValueError(
                f"unsupported recorder page layout for column {index}: "
                f"types {dictionary_page['type']}, {data_page['type']}"
            )
        start = dictionary_page["start"]
        end = data_page["end"]
        total_compressed = end - start
        total_uncompressed = dictionary_page["uncompressed_size"] + data_page["uncompressed_size"]
        _set_field(column_meta, 6, total_uncompressed, TType.I64)
        _set_field(column_meta, 7, total_compressed, TType.I64)
        _set_field(column_meta, 9, data_page["start"], TType.I64)
        _set_field(column_meta, 11, dictionary_page["start"], TType.I64)
        chunk_info.append((start, end))

    row_groups_field = next(value for field_id, field_type, value in metadata if field_id == 4 and field_type == TType.LIST)
    _, groups = row_groups_field
    page_index = 0
    row_count = 0
    for group_index, row_group in enumerate(groups):
        columns_field = next(value for field_id, field_type, value in row_group if field_id == 1 and field_type == TType.LIST)
        _, columns = columns_field
        group_chunks = chunk_info[group_index * len(columns):(group_index + 1) * len(columns)]
        group_uncompressed = 0
        for column_chunk, (_, _) in zip(columns, group_chunks):
            meta_field = next(value for field_id, field_type, value in column_chunk if field_id == 3 and field_type == TType.STRUCT)
            total = _field_value(meta_field, 6)
            if total is not None:
                group_uncompressed += int(total[2])
        _set_field(row_group, 2, group_uncompressed, TType.I64)
        data_pages = [pages[page_index + 1 + offset * 2] for offset in range(len(columns))]
        group_rows = None
        for data_page in data_pages:
            if data_page.get("data_page") and 1 in data_page["data_page"]:
                value = int(data_page["data_page"][1])
                if group_rows is None:
                    group_rows = value
                elif group_rows != value:
                    raise ValueError(f"inconsistent row counts in Parquet row group: {group_rows} vs {value}")
        if group_rows is None:
            raise ValueError("unable to recover Parquet row-group row count")
        _set_field(row_group, 3, group_rows, TType.I64)
        row_count += group_rows
        page_index += len(columns) * 2
    _set_field(metadata, 3, row_count, TType.I64)

    footer = _serialize_thrift_struct(metadata)
    rebuilt = cr_candidate[:footer_start] + footer + len(footer).to_bytes(4, "little") + b"PAR1"
    if _parquet_footer_start(rebuilt) is None:
        raise ValueError("reconstructed Parquet footer is invalid")
    return rebuilt, chunk_info


def _repair_mixed_newlines(lf_candidate: bytes, cr_candidate: bytes) -> bytes | None:
    """Repair transcoded recorder Parquet with structural footer recovery.

    The text export can corrupt both page bytes and compact-Thrift footer
    offsets. The previous repair trusted the LF footer, which can invent
    overlapping chunk bounds (for example PE_ID). We now derive physical chunk
    boundaries from page headers first, rewrite the footer offsets/sizes from
    those boundaries, then use PyArrow only to resolve remaining ambiguous page
    bytes.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
    except ImportError:
        return None

    rebuilt, chunk_info = _repair_footer_and_get_chunks(lf_candidate, cr_candidate)
    if rebuilt is None:
        return None

    if _readable(parquet, pa, rebuilt):
        return rebuilt

    current = bytearray(rebuilt)
    for column_index, (start, end) in enumerate(chunk_info):
        try:
            metadata = parquet.ParquetFile(pa.BufferReader(bytes(current))).metadata
            row_group = metadata.row_group(0)
            name = row_group.column(column_index).path_in_schema
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            name = str(name).split(".")[-1]
        except Exception as exc:
            raise ValueError(f"unable to inspect reconstructed Parquet column {column_index}: {exc}") from exc

        if _readable(parquet, pa, bytes(current), name):
            continue

        ambiguous = [
            offset
            for offset in range(start, end)
            if lf_candidate[offset] != cr_candidate[offset]
        ]
        if not ambiguous:
            raise ValueError(f"unable to reconstruct Parquet column chunk {name}")
        if len(ambiguous) > 16:
            raise ValueError(
                f"unable to safely brute-force Parquet column chunk {name}: "
                f"{len(ambiguous)} ambiguous newline bytes"
            )

        found = None
        for bits in itertools.product((0, 1), repeat=len(ambiguous)):
            trial = bytearray(current)
            for offset, use_lf in zip(ambiguous, bits):
                trial[offset] = lf_candidate[offset] if use_lf else cr_candidate[offset]
            if _readable(parquet, pa, bytes(trial), name):
                found = trial
                break
        if found is None:
            raise ValueError(
                f"unable to reconstruct Parquet column chunk {name} "
                f"({len(ambiguous)} ambiguous newline bytes)"
            )
        current = found

    result = bytes(current)
    return result if _readable(parquet, pa, result) else None


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
