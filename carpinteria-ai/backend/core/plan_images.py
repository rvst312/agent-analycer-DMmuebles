"""
Renderizado de planos PDF a imágenes y recorte por partida.

- render_pdf_to_pngs: convierte cada página del PDF a PNG para que el visor
  muestre imágenes (el <iframe> de PDF se veía como caja negra) y para poder
  recortar zonas.
- crop_bbox_png: recorta la zona de una partida (bbox en % de la página) con
  un margen alrededor, para mostrar el dibujo junto a su partida.
- extract_pdf_text_pages: extrae la capa de texto de cada página (cotas,
  rótulos y mediciones EXACTAS de los PDF vectoriales) para la visión.

Funciones síncronas (CPU-bound): llamarlas con asyncio.to_thread.
"""
import io
import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

RENDER_SCALE = 2.0     # ~144 dpi, buen equilibrio calidad/peso
CROP_PAD_PCT = 4.0     # margen extra alrededor del bbox (en % de la página)
MAX_PAGES = 30         # tope de páginas a renderizar (anti PDF-bomba)
MAX_PIXELS = 40_000_000  # tope de píxeles por página; por encima se reduce la escala


def detect_pdf_rotations(pdf_path: str) -> List[int]:
    """
    Detecta por página el ángulo del TEXTO (0/90/180/270, en sentido antihorario)
    a partir de la matriz de cada carácter. Muchos planos se exportan con el
    contenido girado (sin metadato /Rotate): esto permite renderizarlos derechos.
    Devuelve [] si no se puede analizar (se asume 0 en todas).
    """
    import math
    from collections import Counter

    try:
        import pdfplumber

        rots: List[int] = []
        detalle: List[tuple] = []  # (dominante, ratio) por página, para coherencia de documento
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:MAX_PAGES]:
                chars = page.chars or []
                cnt: Counter = Counter()
                for ch in chars:
                    # Solo LETRAS: los rótulos marcan la orientación de lectura.
                    # Las cotas (dígitos) suelen ir giradas y meten ruido.
                    if not (ch.get("text") or "").isalpha():
                        continue
                    m = ch.get("matrix") or (1, 0, 0, 1, 0, 0)
                    ang = round(math.degrees(math.atan2(m[1], m[0]))) % 360
                    ang = min((0, 90, 180, 270), key=lambda a: min(abs(ang - a), 360 - abs(ang - a)))
                    cnt[ang] += 1
                total_letras = sum(cnt.values())
                if total_letras == 0:
                    rots.append(0)
                    detalle.append((-1, 0.0))   # sin señal: heredará del documento
                    continue
                dominante, n = cnt.most_common(1)[0]
                ratio = n / total_letras
                detalle.append((dominante, ratio))
                if total_letras < 15:
                    rots.append(0)  # poca señal propia: decidirá la coherencia de documento
                    continue
                # Solo corregimos con mayoría clara (evita falsos positivos)
                rots.append(dominante if (dominante != 0 and ratio >= 0.6) else 0)

        # Coherencia de documento: los planos giran TODAS las páginas igual. Si la
        # mayoría confiada del documento es un ángulo θ≠0, las páginas ambiguas
        # cuyo propio dominante coincide con θ se corrigen también.
        confiadas = [r for r in rots if r != 0]
        if confiadas:
            theta = Counter(confiadas).most_common(1)[0][0]
            if len(confiadas) >= max(2, len(rots) // 2):
                for i, r in enumerate(rots):
                    dom, ratio = detalle[i]
                    if r == 0 and ((dom == theta and ratio >= 0.35) or dom == -1):
                        rots[i] = theta
        if any(rots):
            logger.info(f"Rotación detectada en {pdf_path.split('/')[-1]}: {rots}")
        return rots
    except Exception as e:
        logger.warning(f"detect_pdf_rotations: {e} — se asume sin rotación")
        return []


def extract_pdf_text_pages(pdf_path: str, max_pages: int = MAX_PAGES, max_chars: int = 6000) -> List[str]:
    """
    Extrae la CAPA DE TEXTO de cada página del PDF. Muchos planos son vectoriales
    y traen el texto real (cotas "0.59", "H 212cm", rótulos de acabado, mediciones
    Presto): leído así no tiene errores de OCR/visión.

    Devuelve una entrada por página (cadena vacía si no hay texto útil), recortada
    a `max_chars` por un final de línea y con aviso "[texto truncado]" (para que
    no se tome por completa una medición cortada). Se descarta el texto de una página si más del 50 % de sus líneas
    tienen ≤ 2 caracteres (sin contar espacios): las páginas giradas dan basura
    tipo "P C\nA O\nN N" que confundiría a la visión. Nunca lanza: ante cualquier
    error devuelve [] y deja un aviso en el log.
    """
    try:
        import pdfplumber

        textos: List[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:max_pages]:
                texto = (page.extract_text() or "").strip()
                lineas = [l for l in texto.splitlines() if l.strip()]
                if not lineas:
                    textos.append("")
                    continue
                cortas = sum(1 for l in lineas if len("".join(l.split())) <= 2)
                if cortas / len(lineas) > 0.5:
                    textos.append("")  # texto troceado (página girada): no aporta
                    continue
                if len(texto) > max_chars:
                    marca = "\n[texto truncado]"
                    lim = max_chars - len(marca)
                    corte = texto[:lim]
                    if texto[lim] != "\n":
                        # La última fila quedó a medias (p.ej. "1200" → "1"): se quita
                        # entera; si ni la primera cabe completa, no se envía ninguna.
                        corte = corte[:corte.rfind("\n")] if "\n" in corte else ""
                    texto = (corte + marca).lstrip("\n")
                textos.append(texto)
        return textos
    except Exception as e:
        logger.warning(f"extract_pdf_text_pages: {e} — se sigue sin capa de texto")
        return []


def _render_page(pdf, i: int, rotation: int = 0) -> bytes:
    """Renderiza UNA página con escala acotada por MAX_PIXELS y rotación de
    corrección (grados en sentido horario, para compensar texto girado CCW)."""
    page = pdf[i]
    w, h = page.get_size()  # en puntos PDF
    scale = RENDER_SCALE
    if w * h * scale * scale > MAX_PIXELS:
        scale = max(0.3, (MAX_PIXELS / (w * h)) ** 0.5)
        logger.warning(f"Página {i+1} enorme ({w:.0f}×{h:.0f}pt): escala reducida a {scale:.2f}")
    img = page.render(scale=scale).to_pil()
    if rotation in (90, 180, 270):
        # El texto está girado `rotation`° en sentido ANTIHORARIO → compensamos
        # girando la imagen en horario. PIL rota antihorario: usar ángulo negativo.
        img = img.rotate(-rotation, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_pdf_to_pngs(pdf_path: str) -> List[bytes]:
    """Renderiza las páginas del PDF a PNG (máx. MAX_PAGES), corrigiendo la
    orientación de las páginas cuyo contenido esté girado."""
    import pypdfium2 as pdfium

    rots = detect_pdf_rotations(pdf_path)
    pages: List[bytes] = []
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        n = len(pdf)
        if n > MAX_PAGES:
            logger.warning(f"PDF con {n} páginas: se renderizan solo las primeras {MAX_PAGES}")
        for i in range(min(n, MAX_PAGES)):
            rot = rots[i] if i < len(rots) else 0
            pages.append(_render_page(pdf, i, rot))
    finally:
        pdf.close()
    return pages


def render_pdf_page(pdf_path: str, pagina: int) -> Optional[bytes]:
    """Renderiza SOLO la página indicada (1-based), con corrección de orientación."""
    import pypdfium2 as pdfium

    rots = detect_pdf_rotations(pdf_path)
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        if not (1 <= pagina <= min(len(pdf), MAX_PAGES)):
            return None
        rot = rots[pagina - 1] if pagina - 1 < len(rots) else 0
        return _render_page(pdf, pagina - 1, rot)
    finally:
        pdf.close()


def downscale_for_vision(png: bytes, max_side: int = 1400) -> bytes:
    """Reduce una página a tamaño razonable para enviarla a la visión (JPEG)."""
    from PIL import Image

    img = Image.open(io.BytesIO(png))
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def crop_bbox_png(page_png: bytes, bbox_pct: Tuple[float, float, float, float]) -> Optional[bytes]:
    """
    Recorta [x0, y0, x1, y1] (porcentajes 0-100 del ancho/alto de la página),
    ampliado con CROP_PAD_PCT de margen. Devuelve PNG o None si el bbox no es válido.
    """
    from PIL import Image

    try:
        x0, y0, x1, y1 = [float(v) for v in bbox_pct]
    except Exception:
        return None
    if not (0 <= x0 < x1 <= 100 and 0 <= y0 < y1 <= 100):
        return None
    # Descartar recuadros absurdamente pequeños (< 2% de lado)
    if (x1 - x0) < 2 or (y1 - y0) < 2:
        return None

    img = Image.open(io.BytesIO(page_png))
    w, h = img.size
    x0 = max(0.0, x0 - CROP_PAD_PCT) / 100 * w
    x1 = min(100.0, x1 + CROP_PAD_PCT) / 100 * w
    y0 = max(0.0, y0 - CROP_PAD_PCT) / 100 * h
    y1 = min(100.0, y1 + CROP_PAD_PCT) / 100 * h

    crop = img.crop((int(x0), int(y0), int(x1), int(y1)))
    buf = io.BytesIO()
    crop.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def is_pdf(path: str, content_type: Optional[str] = None) -> bool:
    return (content_type == "application/pdf") or path.lower().endswith(".pdf")
