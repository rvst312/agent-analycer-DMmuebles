import os
import logging
import requests
from typing import Optional
from api.schemas.holded import ContactoSchema

logger = logging.getLogger(__name__)

HOLDED_API_KEY = os.getenv("HOLDED_API_KEY", "")
HOLDED_API_URL = "https://api.holded.com/api/invoicing/v1"

def get_headers() -> dict:
    return {
        "key": HOLDED_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def buscar_contacto(nif: str) -> Optional[str]:
    """
    Busca un contacto en Holded por NIF.
    Devuelve el ID del contacto si existe, de lo contrario None.
    """
    url = f"{HOLDED_API_URL}/contacts"
    params = {"query": nif}
    
    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)
        response.raise_for_status()
        
        contactos = response.json()
        if contactos and isinstance(contactos, list) and len(contactos) > 0:
            return contactos[0].get("id")
            
        return None
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout al buscar contacto con NIF {nif} en Holded")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al buscar contacto con NIF {nif} en Holded: {e}")
        return None

def crear_contacto(datos: ContactoSchema) -> Optional[str]:
    """
    Crea un contacto en Holded.
    Devuelve el ID del contacto creado.
    """
    url = f"{HOLDED_API_URL}/contacts"
    
    payload = {
        "name": datos.nombre,
        "code": datos.nif,
        "email": str(datos.email) if datos.email else None,
        "phone": datos.telefono
    }
    
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}
    
    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        # The Holded API returns something like {"status": 1, "id": "contact_id"}
        if result.get("status") == 1:
            return result.get("id")
        else:
            logger.error(f"Holded devolvió error al crear contacto: {result}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout al crear contacto {datos.nombre} en Holded")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error HTTP al crear contacto {datos.nombre} en Holded: {e}")
        return None

def get_or_create_contacto(nif: str, datos: ContactoSchema) -> Optional[str]:
    """
    Orquesta la búsqueda y creación del contacto en Holded.
    """
    contacto_id = buscar_contacto(nif)
    
    if contacto_id:
        logger.info(f"Contacto encontrado en Holded con ID {contacto_id}")
        return contacto_id
        
    logger.info(f"Contacto no encontrado, procediendo a crear: {datos.nombre}")
    
    # Aseguramos que el NIF en datos coincide con el buscado
    if datos.nif != nif:
        datos.nif = nif
        
    return crear_contacto(datos)

def crear_presupuesto(contact_id: str, presupuesto) -> Optional[str]:
    """
    Crea un borrador de presupuesto en Holded.
    Devuelve el ID del documento creado.
    """
    import time
    url = f"{HOLDED_API_URL}/documents/estimate"
    
    items = []
    for linea in presupuesto.lineas:
        items.append({
            "name": linea.descripcion,
            "units": linea.cantidad,
            "subtotal": linea.subtotal,
            "tax": 21
        })
        
    payload = {
        "contactId": contact_id,
        "date": int(time.time()),
        "items": items
    }
    
    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("status") == 1:
            return result.get("id")
        else:
            logger.error(f"Holded devolvió error al crear presupuesto: {result}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout al crear presupuesto para contacto {contact_id} en Holded")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error HTTP al crear presupuesto para contacto {contact_id} en Holded: {e}")
        return None

