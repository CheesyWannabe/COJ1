"""
CSV Online Judge — FastAPI Backend
Endpoints: POST /upload-reference, POST /submit, GET /results
"""

import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from judge import compare_csvs, CompareConfig

app = FastAPI(title="CSV Judge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory session store (replace with Redis/DB for production) ──
sessions: dict[str, dict] = {}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def get_or_create_session(session_id: Optional[str]) -> tuple[str, dict]:
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {"reference": None, "submissions": []}
    return session_id, sessions[session_id]


async def read_csv_bytes(upload: UploadFile) -> bytes:
    if not upload.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted.")
    data = await upload.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // 1_048_576} MB).")
    if not data.strip():
        raise HTTPException(400, "File is empty.")
    return data


@app.post("/upload-reference")
async def upload_reference(
    file: UploadFile = File(...),
    x_session_id: Optional[str] = Header(None),
):
    """Store a CSV as the reference/ground-truth for the session."""
    data = await read_csv_bytes(file)
    session_id, session = get_or_create_session(x_session_id)
    session["reference"] = {"content": data.decode("utf-8", errors="replace"), "filename": file.filename}
    return JSONResponse(
        {"session_id": session_id, "filename": file.filename, "status": "reference stored"},
        headers={"X-Session-Id": session_id},
    )


@app.post("/submit")
async def submit(
    file: UploadFile = File(...),
    label: str = Form(""),
    x_session_id: Optional[str] = Header(None),
    lowercase: bool = Form(True),
    trim: bool = Form(True),
    numeric_tolerance: bool = Form(True),
    tolerance: float = Form(0.01),
    penalize_extra: bool = Form(True),
):
    """Compare a submission CSV against the stored reference and return a score."""
    session_id, session = get_or_create_session(x_session_id)
    if not session.get("reference"):
        raise HTTPException(400, "No reference file uploaded for this session.")

    data = await read_csv_bytes(file)
    cfg = CompareConfig(
        lowercase=lowercase,
        trim=trim,
        numeric_tolerance=numeric_tolerance,
        tolerance=tolerance,
        penalize_extra=penalize_extra,
    )

    try:
        result = compare_csvs(session["reference"]["content"], data.decode("utf-8", errors="replace"), cfg)
    except Exception as exc:
        raise HTTPException(422, f"CSV comparison failed: {exc}") from exc

    entry = {
        "id": str(uuid.uuid4()),
        "label": label or file.filename,
        "filename": file.filename,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    session["submissions"].append(entry)
    return JSONResponse(entry, headers={"X-Session-Id": session_id})


@app.get("/results")
async def get_results(x_session_id: Optional[str] = Header(None)):
    """Return all submission results for the session."""
    session_id, session = get_or_create_session(x_session_id)
    return JSONResponse(
        {"session_id": session_id, "submissions": session["submissions"]},
        headers={"X-Session-Id": session_id},
    )


@app.delete("/results")
async def clear_results(x_session_id: Optional[str] = Header(None)):
    session_id, session = get_or_create_session(x_session_id)
    session["submissions"] = []
    return {"status": "cleared"}
