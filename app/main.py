from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, Form

from app import config
from app.config import ParseMode
from app.models import ProfileResult
from app.services.profile import profile_upload
from app.services.synth import profile_to_csv

app = FastAPI(title="Scrambler API", version="0.1.0")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)


def get_parse_mode(mode: Optional[str]) -> ParseMode:
    if mode is None:
        return ParseMode(config.DEFAULT_PARSE_MODE)
    try:
        return ParseMode(mode)
    except ValueError:
        raise HTTPException(status_code=400, detail="mode must be 'fast' or 'strict'")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("report.html", {"request": request})


@app.post("/api/profile")
async def api_profile(
    file: UploadFile = File(...),
    mode: Optional[str] = None,
) -> ProfileResult:
    parse_mode = get_parse_mode(mode)
    profile = profile_upload(file, mode=parse_mode)
    return profile


@app.post("/api/generate")
async def api_generate(
    file: UploadFile = File(...),
    rows: int = Form(...),
    mode: Optional[str] = Form(None),
    seed: Optional[int] = Form(None),
    decimal_separator: Optional[str] = Form(None),
):
    if rows <= 0:
        raise HTTPException(status_code=400, detail="rows must be positive")
    parse_mode = get_parse_mode(mode)
    profile = profile_upload(file, mode=parse_mode)
    dec_sep = decimal_separator if decimal_separator in {".", ","} else profile.decimal_separator
    csv_bytes = profile_to_csv(profile, rows=rows, seed=seed, decimal_separator=dec_sep)
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=synthetic.csv",
            "X-Profile-Rows": str(profile.row_count),
            "X-Profile-Encoding": profile.encoding,
            "X-Profile-Delimiter": profile.delimiter,
            "X-Profile-Decimal-Separator": dec_sep,
        },
    )
