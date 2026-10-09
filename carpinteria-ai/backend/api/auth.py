import os
import jwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from typing import Any, Dict, List, Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-for-dev")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def _decode_token(jwt_token: str, allowed_roles: List[str]) -> Dict[str, Any]:
    """Decodifica y valida el rol de un JWT. Lanza 401/403 según corresponda."""
    try:
        payload = jwt.decode(jwt_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("role") not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos insuficientes",
        )
    return payload


def verify_jefe_obra_token_flexible(
    request: Request, token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Como verify_jefe_obra_token pero acepta el JWT desde la cabecera
    Authorization: Bearer <token> O desde el query param ?token=<token>.
    El query param es necesario para EventSource (SSE), que no puede enviar
    cabeceras personalizadas.
    """
    auth = request.headers.get("Authorization", "")
    jwt_token = auth[7:] if auth.startswith("Bearer ") else token
    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(jwt_token, ["jefe_obra", "admin"])

def verify_admin_token(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Verifica que el JWT sea válido y que el usuario tenga el rol 'admin'.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        role: str = payload.get("role")
        if role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos de administrador",
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

def verify_jefe_obra_token(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Verifica que el JWT sea válido y que el usuario tenga el rol 'jefe_obra' o 'admin'.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        role: str = payload.get("role")
        if role not in ["jefe_obra", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos de jefe de obra",
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )
