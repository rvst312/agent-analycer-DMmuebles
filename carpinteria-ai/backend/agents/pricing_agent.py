import logging
import os
from typing import List

from api.schemas.estimate import LineaPresupuesto, PlanoAnalizado, Presupuesto
from rag.embeddings import query_precios

logger = logging.getLogger(__name__)

def get_k_labor(tipo: str) -> float:
    """Obtiene el coste de mano de obra según el tipo de componente desde las variables de entorno."""
    env_var_name = f"K_LABOR_{tipo.upper()}"
    k_labor_str = os.environ.get(env_var_name, "0.0")
    try:
        return float(k_labor_str)
    except ValueError:
        logger.warning(f"Valor inválido para {env_var_name}: {k_labor_str}. Usando 0.0")
        return 0.0

_TIPO_PREFIXES = {
    "tablero": "TAB",
    "puerta": "PTA",
    "cajon": "CAJ",
    "cajón": "CAJ",
    "herraje": "HER",
    "barra": "BAR",
    "estante": "EST",
    "armario": "ARM",
    "otro": "OTR",
}

def _gen_codigo(tipo: str, counters: dict) -> str:
    prefix = _TIPO_PREFIXES.get(tipo.lower(), "OTR")
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]:03d}"


def calculate_pricing(plano: PlanoAnalizado, cliente_id: str, on_line_added=None) -> Presupuesto:
    """
    Calcula el presupuesto a partir de un plano analizado.
    Consulta ChromaDB para obtener los precios de los materiales.
    """
    lineas: List[LineaPresupuesto] = []
    total = 0.0
    tipo_counters: dict = {}

    for comp in plano.componentes:
        # 1. Convertir dimensiones a metros
        ancho_m = comp.ancho_cm / 100.0
        largo_m = comp.largo_cm / 100.0

        # 2. Variantes de query RAG — de más específica a más genérica
        tipo_str = comp.tipo.value if hasattr(comp.tipo, "value") else str(comp.tipo)

        # Map vision-agent tipos to catalog equivalents for better semantic matching
        _TIPO_CATALOG = {
            "tablero": "módulo armario tablero",
            "puerta": "puerta armario",
            "cajon": "cajón bandeja extraíble armario",
            "cajón": "cajón bandeja extraíble armario",
            "estante": "balda estante armario",
            "herraje": "herraje accesorio",
            "barra": "barra perchero armario",
            "armario": "armario módulo",
        }
        catalog_hint = _TIPO_CATALOG.get(tipo_str.lower(), tipo_str)

        query_variants = [
            f"{catalog_hint} {comp.material} {comp.acabado}",
            f"{catalog_hint} {comp.acabado}",
            f"{catalog_hint} {comp.material}",
            f"{tipo_str} {comp.material} {comp.acabado}",
            f"{comp.material} {comp.acabado}",
            f"{catalog_hint}",
        ]

        # 3. Consultar RAG: por cada variante intenta cliente y luego catálogo "general".
        # Se recogen hasta 5 candidatos por variante y se elige el de menor distancia global.
        # Threshold 1.8 — embeddings all-MiniLM-L6-v2 cosine distance, 1.5 era demasiado estricto
        # para descripciones cortas del agente de visión vs materiales detallados del catálogo.
        precio_unitario = 0.0
        precio_pendiente = True
        mejor_distancia = float("inf")
        best_query = query_variants[0]

        for query_text in query_variants:
            for client_key in dict.fromkeys([cliente_id, "general"]):
                resultados = query_precios(query_text, client_key, n_results=5)
                for res in resultados:
                    dist = res.get("distancia", float("inf"))
                    if dist < mejor_distancia and dist < 1.8:
                        metadatos = res.get("metadatos", {})
                        if "precio_unitario" in metadatos:
                            try:
                                precio_unitario = float(metadatos["precio_unitario"])
                                mejor_distancia = dist
                                precio_pendiente = False
                                best_query = query_text
                                if client_key != cliente_id:
                                    logger.info(f"Precio en catálogo 'general': '{query_text}'")
                            except (ValueError, TypeError):
                                logger.error(f"precio_unitario inválido en RAG para {query_text}: {metadatos.get('precio_unitario')}")
            if not precio_pendiente:
                break  # primera variante que resuelve precio es suficiente

        if not precio_pendiente:
            logger.info(f"Precio asignado para '{best_query}': {precio_unitario} (dist={mejor_distancia:.3f})")
        else:
            logger.info(f"Sin precio RAG para '{query_variants[0]}', marcando como pendiente")
        
        # 4. Calcular coste base por unidad
        # Area en m2 * precio por m2
        coste_material = ancho_m * largo_m * precio_unitario
        
        # Para herrajes o barras, el precio podría no ser por m2, pero la fórmula del issue dice:
        # C_total = (ancho_m × largo_m × precio_unitario) + k_labor
        # Asumiremos esta fórmula para todos, si es por unidad, el ancho y largo podrían ser 1, pero seguiremos la fórmula pedida.
        
        k_labor = get_k_labor(comp.tipo.value)
        coste_unitario_total = coste_material + k_labor
        
        # 5. Calcular subtotal de la línea
        subtotal = coste_unitario_total * comp.cantidad
        
        if not precio_pendiente:
            total += subtotal
            
        descripcion = f"{comp.tipo.value.capitalize()} de {comp.material} {comp.acabado} ({comp.ancho_cm}x{comp.largo_cm}cm)"
        if comp.notas:
            descripcion += f" - {comp.notas}"

        codigo = _gen_codigo(comp.tipo.value, tipo_counters)

        linea = LineaPresupuesto(
            codigo=codigo,
            ref=getattr(comp, "ref", None),
            descripcion=descripcion,
            cantidad=comp.cantidad,
            precio_unitario=coste_unitario_total,
            subtotal=subtotal,
            precio_pendiente=precio_pendiente
        )
        lineas.append(linea)
        if on_line_added:
            on_line_added(linea.model_dump())

    return Presupuesto(
        plano_id=plano.plano_id,
        lineas=lineas,
        total=total
    )
