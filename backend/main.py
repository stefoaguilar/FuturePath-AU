
from fastapi import FastAPI

# Create the FuturePath AU backend application
app = FastAPI(
    title="FuturePath AU API",
    description="Backend API for the FuturePath AU cybersecurity pathway navigator.",
    version="0.1.0"
)


# Main endpoint
@app.get("/")
def home():
    return {
        "message": "FuturePath AU backend is running!",
        "application": "FuturePath AU",
        "version": "0.1.0"
    }


# Health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "FuturePath AU API is operational"
    }
