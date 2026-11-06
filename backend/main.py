
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


# Locate Samer's dataset from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "opportunities.json"


# Create the FuturePath AU backend.
app = FastAPI(
    title="FuturePath AU API",
    description="Backend API for the FuturePath AU cybersecurity pathway navigator.",
    version="0.1.0"
)


# Allow Hakm's local React application to access the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_methods=["GET"],
    allow_headers=["*"]
)


# Existing homepage endpoint.
@app.get("/")
def home():
    return {
        "message": "FuturePath AU backend is running!",
        "application": "FuturePath AU",
        "version": "0.1.0"
    }


# Existing health-check endpoint.
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "FuturePath AU API is operational"
    }


# New opportunity catalogue endpoint.
@app.get("/api/opportunities")
def get_opportunities():
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            dataset = json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        raise HTTPException(
            status_code=500,
            detail="Opportunity dataset is unavailable or invalid."
        )

    # Check the minimum required response structure.
    if (
        not isinstance(dataset, dict)
        or not isinstance(dataset.get("opportunities"), list)
    ):
        raise HTTPException(
            status_code=500,
            detail="Opportunity dataset has an invalid structure."
        )

    return dataset
