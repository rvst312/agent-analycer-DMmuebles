"""
Limitador de peticiones (rate limiting) compartido, basado en slowapi.

Se define aquí (y no en main.py) para poder importarlo tanto desde main.py
(registro del middleware/handler) como desde las rutas que lo decoran, sin
crear imports circulares.
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_ip(request) -> str:
    """
    Clave por IP del cliente. Detrás del proxy de Railway la IP real viaja en
    la cabecera X-Forwarded-For; sin ella caemos a la IP directa de la conexión.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)

# Límite del endpoint de login (configurable por env). Protege contra fuerza bruta.
LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "10/minute")
