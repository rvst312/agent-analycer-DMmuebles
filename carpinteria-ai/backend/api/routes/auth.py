import os
from datetime import datetime, timedelta, timezone

import jwt
from api.auth import JWT_ALGORITHM, JWT_SECRET
from core.rate_limit import LOGIN_RATE_LIMIT, limiter
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Auth"])

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
@limiter.limit(LOGIN_RATE_LIMIT)
def login(request: Request, req: LoginRequest):
    if req.username != ADMIN_USERNAME or req.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    payload = {
        "sub": req.username,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}
