import csv
import io
from typing import Any

from chusky_bridge.parsers.errors import ParseError


def parse_csv(data: bytes, *, delimiter: str = ",", max_rows: int = 1000) -> dict[str, Any]:
    if len(delimiter) != 1:
        raise ParseError("delimiter must be a single character")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("file is not valid UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ParseError("CSV has no header row")

    records: list[dict[str, Any]] = []
    for row in reader:
        if len(records) >= max_rows:
            break
        records.append({key: value for key, value in row.items() if key is not None})

    return {
        "format": "csv",
        "columns": list(reader.fieldnames),
        "record_count": len(records),
        "records": records,
    }
