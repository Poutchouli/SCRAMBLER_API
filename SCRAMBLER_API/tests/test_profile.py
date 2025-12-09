import io
import tempfile

import pytest
from fastapi import HTTPException, UploadFile

from app import config
from app.config import ParseMode
from app.models import FieldType
from app.services import profile as profile_service


def test_profile_infers_types_and_lengths():
    csv_text = """a,b,c
1,hello,TRUE
2,world,false
,hi,
"""
    result = profile_service.profile_from_text(csv_text, parse_mode=ParseMode.STRICT)
    assert result.row_count == 3

    a = next(f for f in result.fields if f.name == "a")
    b = next(f for f in result.fields if f.name == "b")
    c = next(f for f in result.fields if f.name == "c")

    assert a.type.name.lower() == "integer"
    assert a.nullable is True
    assert b.min_length == 2 and b.max_length == 5
    assert c.type.name.lower() == "boolean"
    assert pytest.approx(c.null_fraction, rel=1e-2) == 1 / 3


def test_profile_enforces_row_limit():
    # build CSV with MAX_ROWS + 1 data rows
    header = "col\n"
    rows = "\n".join(["1" for _ in range(config.MAX_ROWS + 1)])
    csv_text = header + rows
    with pytest.raises(HTTPException) as exc:
        profile_service.profile_from_text(csv_text, parse_mode=ParseMode.STRICT)
    assert exc.value.status_code == 400
    assert "Row limit" in exc.value.detail


def test_validate_csv_upload_rejects_non_csv():
    fake_file = tempfile.SpooledTemporaryFile()
    fake_file.write(b"{}")
    fake_file.seek(0)
    upload = UploadFile(filename="data.json", file=fake_file, headers={"content-type": "application/json"})
    with pytest.raises(HTTPException) as exc:
        profile_service.validate_csv_upload(upload)
    assert exc.value.status_code == 415
    assert "CSV" in exc.value.detail


def test_detects_semicolon_delimiter():
    csv_text = """a;b;c
1;2;3
4;5;6
"""
    result = profile_service.profile_from_text(csv_text, delimiter=None, parse_mode=ParseMode.STRICT)
    assert result.row_count == 2
    assert [f.name for f in result.fields] == ["a", "b", "c"]


def test_detects_latin1_encoding_and_tab_delimiter():
    raw = "café\tval\nélan\t7\n".encode("latin-1")
    limited = profile_service.enforce_limits(raw)
    text, enc = profile_service.decode_content(limited)
    assert enc.lower() in {"latin-1", "iso-8859-1", "cp1252"}
    delim = profile_service.detect_delimiter(text)
    assert delim == "\t"
    result = profile_service.profile_from_text(text, delimiter=delim, parse_mode=ParseMode.STRICT, encoding=enc)
    assert result.row_count == 1


def test_detects_date_datetime_and_decimal():
    csv_text = """d,dt,price
2024-01-02,2024-01-02T10:00:00,12.345
2024-01-03,2024-01-04 11:00:00,15.500
"""
    result = profile_service.profile_from_text(csv_text, parse_mode=ParseMode.STRICT)
    types = {f.name: f.type for f in result.fields}
    assert types["d"] == FieldType.DATE
    assert types["dt"] == FieldType.DATETIME
    assert types["price"] in {FieldType.DECIMAL, FieldType.FLOAT}
    d_field = next(f for f in result.fields if f.name == "d")
    assert d_field.date_min is not None and d_field.date_max is not None
    assert result.decimal_separator == "."
