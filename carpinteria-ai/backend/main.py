"""
Entry point FastAPI
"""
from fastapi import FastAPI
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Carpintería AI API")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API de Carpintería AI en funcionamiento"}

@app.post("/estimates")
def create_estimate():
    pass

@app.post("/resume")
def resume_workflow():
    pass
