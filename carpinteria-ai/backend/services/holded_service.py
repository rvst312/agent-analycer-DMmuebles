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

def _agrupar_lineas_por_ref(presupuesto) -> list:
    """
    Agrupa las líneas por ref y devuelve una lista de items para Holded.
    Primer item: título del proyecto completo (editable desde el visualizador),
    a precio 0. Luego, un item por cada ref (A01, E02…): nombre=ref,
    desc=descripción comercial de 3 líneas, subtotal=suma del grupo.
    Las líneas pendientes de precio se excluyen del subtotal. Sin IVA (tax=0).
    """
    from collections import defaultdict

    grupos: dict = defaultdict(list)
    for linea in presupuesto.lineas:
        key = (linea.ref or "SIN-REF").strip()
        grupos[key].append(linea)

    descripciones_grupo: dict = getattr(presupuesto, "descripciones_grupo", None) or {}
    titulo_proyecto = getattr(presupuesto, "titulo_proyecto", None) or presupuesto.plano_id

    items = [{
        "name": titulo_proyecto,
        "units": 1,
        "subtotal": 0,
        "tax": 0,
    }]

    for ref, lineas in grupos.items():
        precio_grupo = sum(
            l.subtotal for l in lineas if not l.precio_pendiente
        )
        desc = descripciones_grupo.get(ref) or _generar_descripcion(ref, lineas)
        items.append({
            "name": ref,
            "desc": desc,
            "units": 1,
            "subtotal": round(precio_grupo, 2),
            "tax": 0,
        })

    return items


def _generar_descripcion(ref: str, lineas: list) -> str:
    """Descripción de fallback cuando el frontend no envió una descripción de grupo."""
    partes = [f"Módulo {ref} según plano."]
    for l in lineas:
        estado = " (precio pendiente)" if l.precio_pendiente else ""
        partes.append(f"- {l.descripcion} × {l.cantidad}{estado}")
    return "\n".join(partes)


def crear_presupuesto(contact_id: str, presupuesto) -> Optional[str]:
    """
    Crea un borrador de presupuesto en Holded agrupado por referencia de plano.
    Cada ref (A01, A02…) genera un único item; el desglose queda sólo en BD.
    Devuelve el ID del documento creado.
    """
    import time
    url = f"{HOLDED_API_URL}/documents/estimate"

    items = _agrupar_lineas_por_ref(presupuesto)
    logger.info(
        f"Enviando a Holded {len(items)} grupo(s): "
        + ", ".join(f"{i['name']}={i['subtotal']}€" for i in items)
    )

    payload = {
        "contactId": contact_id,
        "date": int(time.time()),
        "items": items,
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

