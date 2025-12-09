import pathlib
from typing import Optional

import typer

from app import config
from app.config import ParseMode
from app.services.profile import (
    enforce_limits,
    profile_from_text,
    decode_content,
    detect_delimiter,
)
from app.services.synth import profile_to_csv

app = typer.Typer(help="Scrambler CLI")


def _read_file(path: pathlib.Path) -> str:
    data = path.read_bytes()
    limited = enforce_limits(data)
    text, _ = decode_content(limited)
    return text


@app.command()
def profile(
    file: pathlib.Path = typer.Argument(..., exists=True, readable=True, help="CSV file to profile"),
    mode: ParseMode = typer.Option(ParseMode.FAST, help="fast or strict"),
):
    text = _read_file(file)
    delimiter = detect_delimiter(text)
    result = profile_from_text(text, delimiter=delimiter, parse_mode=mode, encoding="utf-8")
    typer.echo(result.json(indent=2))


@app.command()
def generate(
    file: pathlib.Path = typer.Argument(..., exists=True, readable=True, help="CSV file to profile"),
    rows: int = typer.Option(1000, help="Rows to synthesize (<=100000)"),
    output: pathlib.Path = typer.Option(pathlib.Path("synthetic.csv"), help="Output CSV path"),
    seed: Optional[int] = typer.Option(None, help="Optional RNG seed"),
    mode: ParseMode = typer.Option(ParseMode.FAST, help="fast or strict"),
    decimal_separator: Optional[str] = typer.Option(None, help="Override decimal separator: '.' or ','"),
):
    if rows <= 0 or rows > config.MAX_ROWS:
        raise typer.BadParameter("rows must be between 1 and 100000")
    text = _read_file(file)
    delimiter = detect_delimiter(text)
    profile_result = profile_from_text(text, delimiter=delimiter, parse_mode=mode, encoding="utf-8")
    dec_sep = decimal_separator if decimal_separator in {".", ","} else profile_result.decimal_separator
    csv_bytes = profile_to_csv(profile_result, rows=rows, seed=seed, decimal_separator=dec_sep)
    output.write_bytes(csv_bytes)
    typer.echo(f"Wrote {rows} rows to {output}")


if __name__ == "__main__":
    app()
