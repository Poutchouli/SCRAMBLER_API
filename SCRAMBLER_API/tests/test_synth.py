import csv
import io

import pytest
from fastapi import HTTPException

from app import config
from app.models import FieldConstraint, FieldType, ProfileResult
from app.services.synth import generate_rows, profile_to_csv


def basic_profile() -> ProfileResult:
    return ProfileResult(
        row_count=2,
        fields=[
            FieldConstraint(
                name="name",
                type=FieldType.STRING,
                nullable=True,
                min_length=3,
                max_length=5,
                null_fraction=0.8,
            ),
            FieldConstraint(
                name="age",
                type=FieldType.INTEGER,
                nullable=False,
                min_value=18,
                max_value=21,
            ),
        ],
    )


def test_generate_rows_respects_seed():
    profile = basic_profile()
    csv_a = profile_to_csv(profile, rows=3, seed=123)
    csv_b = profile_to_csv(profile, rows=3, seed=123)
    assert csv_a == csv_b

    # different seed should differ
    csv_c = profile_to_csv(profile, rows=3, seed=456)
    assert csv_a != csv_c


def test_generate_rows_enforces_row_limit():
    profile = basic_profile()
    with pytest.raises(HTTPException):
        list(generate_rows(profile, rows=config.MAX_ROWS + 1))


def test_generate_respects_null_probability():
    profile = basic_profile()
    rows = list(generate_rows(profile, rows=1, seed=1))
    first_value = rows[0][0]
    assert first_value == ""


def test_profile_to_csv_outputs_header_and_rows():
    profile = basic_profile()
    data = profile_to_csv(profile, rows=2, seed=42)
    reader = csv.reader(io.StringIO(data.decode("utf-8")))
    rows = list(reader)
    assert rows[0] == ["name", "age"]
    assert len(rows) == 3  # header + 2 data rows


def test_integer_generation_with_allowed_values_stays_numeric_and_bounded():
    profile = ProfileResult(
        row_count=1,
        fields=[
            FieldConstraint(
                name="score",
                type=FieldType.INTEGER,
                nullable=False,
                min_value=10,
                max_value=20,
                allowed_values=["11", "15", "19"],
            )
        ],
    )
    vals = [row[0] for row in generate_rows(profile, rows=20, seed=123)]
    for v in vals:
        as_int = int(v)
        assert 10 <= as_int <= 20


def test_float_generation_with_allowed_values_stays_numeric_and_bounded():
    profile = ProfileResult(
        row_count=1,
        fields=[
            FieldConstraint(
                name="ratio",
                type=FieldType.FLOAT,
                nullable=False,
                min_value=0.5,
                max_value=1.5,
                allowed_values=["0.9", "1.2"],
            )
        ],
    )
    vals = [row[0] for row in generate_rows(profile, rows=20, seed=456)]
    for v in vals:
        as_float = float(v)
        assert 0.5 <= as_float <= 1.5


def test_decimal_and_date_generation_respects_bounds():
    profile = ProfileResult(
        row_count=1,
        fields=[
            FieldConstraint(
                name="amount",
                type=FieldType.DECIMAL,
                nullable=False,
                min_value=1.1,
                max_value=2.2,
                allowed_values=["1.5", "2.0"],
            ),
            FieldConstraint(
                name="when",
                type=FieldType.DATE,
                nullable=False,
                date_min="2024-01-01",
                date_max="2024-01-10",
            ),
        ],
        encoding="utf-8",
        delimiter=",",
        decimal_separator=",",
    )
    rows = list(generate_rows(profile, rows=10, seed=789))
    for amt, when in rows:
        amt_clean = amt.replace(",", ".")
        amt_f = float(amt_clean)
        assert 1.1 <= amt_f <= 2.2
        assert when >= "2024-01-01" and when <= "2024-01-10"
