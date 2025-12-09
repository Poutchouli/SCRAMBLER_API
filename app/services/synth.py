import csv
import io
import random
import string
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Iterable, List

from fastapi import HTTPException

from app import config
from app.models import FieldConstraint, FieldType, ProfileResult


def _null_probability(constraint: FieldConstraint) -> float:
    return min(max(constraint.null_fraction, 0.0), 0.9)


def _parsed_allowed_numbers(allowed: List[str] | None, cast):
    if not allowed:
        return []
    parsed = []
    for val in allowed:
        try:
            parsed.append(cast(val))
        except Exception:
            continue
    return parsed


def _scrambled_token(min_len: int, max_len: int) -> str:
    # Generate high-entropy token within bounds; if bounds are too small, clamp to at least 1
    min_len = max(1, min_len)
    max_len = max(min_len, max_len)
    length = random.randint(min_len, max_len)
    alphabet = string.ascii_letters + string.digits + "_-+=@#%&$!*"  # richer noise
    return "".join(random.choices(alphabet, k=length))


def _mutate_string(base: str, min_len: int, max_len: int) -> str:
    # Always produce a new, high-entropy token—base is only used to influence length bounds
    return _scrambled_token(min_len, max_len)


def _generate_value(constraint: FieldConstraint, decimal_sep: str = ".") -> str:
    if random.random() < _null_probability(constraint) and constraint.nullable:
        return ""

    if constraint.type == FieldType.BOOLEAN:
        return random.choice(["true", "false"])

    if constraint.type == FieldType.INTEGER:
        allowed_ints = _parsed_allowed_numbers(constraint.allowed_values, int)
        low = int(constraint.min_value) if constraint.min_value is not None else 0
        high = int(constraint.max_value) if constraint.max_value is not None else max(low + 1, 1000)
        if low == high:
            high = low + 10
        if allowed_ints:
            choice = random.choice(allowed_ints)
            jitter = random.randint(-5, 5)
            candidate = max(low, min(high, choice + jitter))
            return str(candidate)
        return str(random.randint(low, high))

    if constraint.type == FieldType.FLOAT:
        allowed_floats = _parsed_allowed_numbers(constraint.allowed_values, float)
        low = constraint.min_value if constraint.min_value is not None else 0.0
        high = constraint.max_value if constraint.max_value is not None else max(low + 1.0, 1000.0)
        if low == high:
            high = low + 1.0
        if allowed_floats:
            choice = random.choice(allowed_floats)
            span = max(0.1, (high - low) * 0.05)
            candidate = max(low, min(high, choice + random.uniform(-span, span)))
            out = f"{candidate:.3f}"
            return out.replace(".", decimal_sep) if decimal_sep == "," else out
        out = f"{random.uniform(low, high):.3f}"
        return out.replace(".", decimal_sep) if decimal_sep == "," else out

    if constraint.type == FieldType.DECIMAL:
        allowed_decimals = _parsed_allowed_numbers(constraint.allowed_values, Decimal)
        low = Decimal(str(constraint.min_value)) if constraint.min_value is not None else Decimal("0")
        high = Decimal(str(constraint.max_value)) if constraint.max_value is not None else Decimal("1000")
        if low == high:
            high = low + Decimal("1")
        if allowed_decimals:
            choice = random.choice(allowed_decimals)
            span = (high - low) * Decimal("0.05")
            candidate = choice + Decimal(random.uniform(-float(span), float(span)))
            candidate = min(high, max(low, candidate))
        else:
            candidate = low + (high - low) * Decimal(str(random.random()))
        out = format(candidate.quantize(Decimal("0.001")), "f")
        return out.replace(".", decimal_sep) if decimal_sep == "," else out

    if constraint.type in {FieldType.DATE, FieldType.DATETIME}:
        default_start = datetime.now() - timedelta(days=365)
        default_end = datetime.now()
        start = datetime.fromisoformat(constraint.date_min) if constraint.date_min else default_start
        end = datetime.fromisoformat(constraint.date_max) if constraint.date_max else default_end
        if start >= end:
            end = start + timedelta(days=1)
        delta_seconds = int((end - start).total_seconds())
        offset = random.randint(0, max(1, delta_seconds))
        sample_dt = start + timedelta(seconds=offset)
        if constraint.type == FieldType.DATE:
            return sample_dt.date().isoformat()
        return sample_dt.isoformat(sep="T", timespec="seconds")

    # Strings (and everything else defaults to scrambled strings)
    if constraint.allowed_values:
        candidate = random.choice(constraint.allowed_values)
        min_len = constraint.min_length or max(1, len(candidate))
        max_len = constraint.max_length or max(min_len, len(candidate) + 8)
        return _mutate_string(candidate, min_len, max_len)

    min_len = constraint.min_length or 8
    max_len = constraint.max_length or max(min_len + 8, 24)
    if max_len < min_len:
        max_len = min_len
    return _scrambled_token(min_len, max_len)


def generate_rows(profile: ProfileResult, rows: int, seed: int | None = None) -> Iterable[List[str]]:
    if rows > config.MAX_ROWS:
        raise HTTPException(status_code=400, detail="Requested rows exceed 100k limit")
    if seed is not None:
        random.seed(seed)
    constraints = profile.fields
    decimal_sep = getattr(profile, "decimal_separator", ".") or "."
    for _ in range(rows):
        yield [_generate_value(c, decimal_sep=decimal_sep) for c in constraints]


def profile_to_csv(profile: ProfileResult, rows: int, seed: int | None = None, decimal_separator: str | None = None) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=profile.delimiter)
    dec_sep = decimal_separator or getattr(profile, "decimal_separator", ".") or "."
    writer.writerow([c.name for c in profile.fields])
    for row in generate_rows(profile, rows, seed):
        writer.writerow(row)
    data = output.getvalue()
    if dec_sep != ".":
        data = data.replace(".", dec_sep)
    return data.encode(profile.encoding or "utf-8")
