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

def calculate_pricing(plano: PlanoAnalizado, cliente_id: str, on_line_added=None) -> Presupuesto:
    """
    Calcula el presupuesto a partir de un plano analizado.
    Consulta ChromaDB para obtener los precios de los materiales.
    """
    lineas: List[LineaPresupuesto] = []
    total = 0.0

    for comp in plano.componentes:
        # 1. Convertir dimensiones a metros
        ancho_m = comp.ancho_cm / 100.0
        largo_m = comp.largo_cm / 100.0
        
        # 2. Construir query para RAG
        # Usamos material, acabado y tipo para buscar la mejor coincidencia
        query_text = f"{comp.material} {comp.acabado} {comp.tipo}"
        
        # 3. Consultar RAG
        version_vigente = os.environ.get("PRECIOS_VERSION", "1.0")
        resultados = query_precios(query_text, cliente_id, version=version_vigente, n_results=1)
        
        precio_unitario = 0.0
        precio_pendiente = True
        
        if resultados:
            # Tomamos el primer resultado
            mejor_resultado = resultados[0]
            distancia = mejor_resultado.get("distancia", 0.0)
            
            # En ChromaDB L2 distance, valores más bajos son mejores.
            # Solo consideramos válido si la distancia es menor a un umbral (ej. 1.0)
            if distancia < 1.0:
                metadatos = mejor_resultado.get("metadatos", {})
                if "precio_unitario" in metadatos:
                    try:
                        precio_unitario = float(metadatos["precio_unitario"])
                        precio_pendiente = False
                    except (ValueError, TypeError):
                        logger.error(f"precio_unitario inválido en RAG para {query_text}: {metadatos.get('precio_unitario')}")
            else:
                logger.info(f"No se encontró precio confiable para {query_text}. Distancia: {distancia}")
        
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
            
        linea = LineaPresupuesto(
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
