import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from charset_normalizer import from_bytes
from fastapi import HTTPException, UploadFile

from app import config
from app.config import ParseMode
from app.models import FieldConstraint, FieldType, ProfileResult


@dataclass
class FieldStats:
    name: str
    type_counts: Dict[FieldType, int] = field(default_factory=lambda: {t: 0 for t in FieldType})
    max_len: int = 0
    min_len: Optional[int] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    allowed_values: set = field(default_factory=set)
    nulls: int = 0
    min_date: Optional[datetime] = None
    max_date: Optional[datetime] = None

    def register(self, value: str, detected_type: FieldType) -> None:
        self.type_counts[detected_type] += 1
        if value == "":
            self.nulls += 1
            return
        length = len(value)
        self.max_len = max(self.max_len, length)
        self.min_len = length if self.min_len is None else min(self.min_len, length)
        if detected_type in {FieldType.INTEGER, FieldType.FLOAT, FieldType.DECIMAL}:
            numeric = normalize_numeric(value)
            if numeric is not None:
                self.min_val = numeric if self.min_val is None else min(self.min_val, numeric)
                self.max_val = numeric if self.max_val is None else max(self.max_val, numeric)
        if detected_type in {FieldType.DATE, FieldType.DATETIME}:
            dt = parse_datetime(value)
            if dt:
                self.min_date = dt if self.min_date is None else min(self.min_date, dt)
                self.max_date = dt if self.max_date is None else max(self.max_date, dt)
        # keep small cardinality sets only
        if len(self.allowed_values) < 50:
            self.allowed_values.add(value)


def enforce_limits(content: bytes) -> bytes:
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (50 MB limit)")
    return content


def detect_encoding(content: bytes) -> Tuple[str, float]:
    result = from_bytes(content[:1_000_000]).best()
    if result and result.encoding:
        try:
            score = float(result.fingerprint or 0)
        except Exception:
            score = 0.0
        enc = result.encoding
        sample = content[:256]
        if enc.lower().startswith("utf_16") and b"\x00" not in sample:
            enc = "latin-1"
        return enc, score
    return "utf-8", 0.0


def decode_content(content: bytes) -> Tuple[str, str]:
    encoding, _score = detect_encoding(content)
    try:
        return content.decode(encoding), encoding
    except UnicodeDecodeError:
        try:
            return content.decode("utf-8", errors="replace"), "utf-8"
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Unable to decode file")


def detect_type(raw: str) -> FieldType:
    if raw == "" or raw is None:
        return FieldType.EMPTY
    lower = raw.strip().lower()
    if lower in {"true", "false", "1", "0", "yes", "no"}:
        return FieldType.BOOLEAN
    dt = parse_datetime(raw)
    if dt:
        return FieldType.DATETIME if dt.time() != datetime.min.time() else FieldType.DATE
    try:
        int(lower)
        return FieldType.INTEGER
    except ValueError:
        pass
    sep = detect_decimal_separator(raw)
    if sep:
        normalized = raw.strip()
        if sep == ",":
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
        try:
            Decimal(normalized)
            return FieldType.DECIMAL
        except InvalidOperation:
            pass
    try:
        Decimal(lower)
        if any(ch in lower for ch in [".", "e", "E", ","]):
            return FieldType.DECIMAL
    except InvalidOperation:
        pass
    try:
        float(lower)
        return FieldType.FLOAT
    except ValueError:
        return FieldType.STRING


def parse_datetime(raw: str) -> Optional[datetime]:
    txt = raw.strip()
    if not txt:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(txt, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(txt)
    except Exception:
        return None


def detect_decimal_separator(raw: str) -> Optional[str]:
    txt = raw.strip()
    if not txt:
        return None
    if re.match(r"^[+-]?\d{1,3}(?:[.,]\d+)+$", txt):
        return "," if "," in txt else "."
    if re.match(r"^[+-]?\d+[.,]\d+$", txt):
        return "," if "," in txt else "."
    return None


def normalize_numeric(raw: str) -> Optional[float]:
    txt = raw.strip()
    if not txt:
        return None
    sep = detect_decimal_separator(txt)
    candidate = txt
    if sep == ",":
        candidate = candidate.replace(".", "").replace(",", ".")
    elif sep == ".":
        candidate = candidate.replace(",", "")
    try:
        return float(candidate)
    except ValueError:
        try:
            return float(txt)
        except ValueError:
            return None


def pick_final_type(type_counts: Dict[FieldType, int]) -> FieldType:
    # prioritize non-empty counts, otherwise mark empty
    non_zero = {t: c for t, c in type_counts.items() if c > 0 and t != FieldType.EMPTY}
    if not non_zero:
        return FieldType.EMPTY
    # prefer most frequent; tie-breaker by specificity
    ordered = sorted(non_zero.items(), key=lambda item: item[1], reverse=True)
    return ordered[0][0]


def detect_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        # heuristic fallback
        if sample.count(";") > sample.count(",") and sample.count(";") > 0:
            return ";"
        if sample.count("|") > sample.count(",") and sample.count("|") > 0:
            return "|"
        if sample.count("\t") > 0:
            return "\t"
        return ","


def profile_from_text(text: str, delimiter: Optional[str] = None, parse_mode: ParseMode = ParseMode.FAST, encoding: str = "utf-8") -> ProfileResult:
    delim = delimiter or detect_delimiter(text)
    csv_buffer = io.StringIO(text)
    reader = csv.DictReader(csv_buffer, delimiter=delim)
    headers = reader.fieldnames or []
    stats: Dict[str, FieldStats] = {h: FieldStats(name=h) for h in headers}
    decimal_separators: set[str] = set()

    row_limit = config.MAX_ROWS
    sample_limit = config.FAST_SAMPLE_ROWS if parse_mode == ParseMode.FAST else None

    for idx, row in enumerate(reader, start=1):
        if idx > row_limit:
            raise HTTPException(status_code=400, detail="Row limit exceeded (100k max)")
        if sample_limit and idx > sample_limit:
            break
        for header in headers:
            raw = row.get(header, "") or ""
            sep = detect_decimal_separator(raw)
            if sep:
                decimal_separators.add(sep)
            detected = detect_type(raw)
            stats[header].register(raw, detected)
    total_rows = min(idx if 'idx' in locals() else 0, sample_limit or idx)

    constraints: List[FieldConstraint] = []
    for header in headers:
        field_stat = stats[header]
        final_type = pick_final_type(field_stat.type_counts)
        nullable = field_stat.nulls > 0
        allowed_values_list: Optional[List[str]] = None
        if field_stat.allowed_values and len(field_stat.allowed_values) <= 50:
            allowed_values_list = sorted(list(field_stat.allowed_values))
        constraints.append(
            FieldConstraint(
                name=header,
                type=final_type,
                nullable=nullable,
                min_length=field_stat.min_len,
                max_length=field_stat.max_len,
                min_value=field_stat.min_val,
                max_value=field_stat.max_val,
                allowed_values=allowed_values_list,
                null_fraction=(field_stat.nulls / total_rows) if total_rows else 0,
                date_min=field_stat.min_date.isoformat() if field_stat.min_date else None,
                date_max=field_stat.max_date.isoformat() if field_stat.max_date else None,
            )
        )

    decimal_sep = "," if "," in decimal_separators and "." not in decimal_separators else "."
    return ProfileResult(row_count=total_rows, fields=constraints, encoding=encoding, delimiter=delim, decimal_separator=decimal_sep)


def profile_upload(file: UploadFile, mode: ParseMode = ParseMode.FAST) -> ProfileResult:
    validate_csv_upload(file)
    content = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    limited = enforce_limits(content)
    text, encoding = decode_content(limited)
    delimiter = detect_delimiter(text)
    return profile_from_text(text, delimiter=delimiter, parse_mode=mode, encoding=encoding)


def validate_csv_upload(file: UploadFile) -> None:
    allowed = {"text/csv", "application/vnd.ms-excel", "application/csv"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Invalid content type; only CSV allowed")
