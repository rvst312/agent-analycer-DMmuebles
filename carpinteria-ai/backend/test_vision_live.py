"""
Script de prueba rápida del vision agent con un plano real.
Uso: python test_vision_live.py <ruta_imagen>
"""
import base64
import json
import sys
import os

# Asegura que los imports del proyecto funcionen
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from agents.vision_agent import analyze_plan, _detect_view_codes
import anthropic

def run_test(image_path: str):
    print(f"\n{'='*60}")
    print(f"  PLANO: {os.path.basename(image_path)}")
    print(f"{'='*60}\n")

    # Cargar imagen
    ext = os.path.splitext(image_path)[1].lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
    media_type = media_types.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        image_base64 = base64.standard_b64encode(f.read()).decode("utf-8")

    # ── PASADA 1: códigos de vista ──
    print("[ PASADA 1 ] Detectando códigos de vista...")
    client = anthropic.Anthropic()
    codes = _detect_view_codes(client, image_base64, media_type, "test")
    print(f"  → Códigos detectados: {codes if codes else '(ninguno)'}\n")

    # ── PASADA 2: extracción completa ──
    print("[ PASADA 2 ] Extrayendo componentes...")
    resultado = analyze_plan(
        image_base64=image_base64,
        media_type=media_type,
        plano_id="test-live",
    )

    if resultado.error:
        print(f"  ✗ ERROR: {resultado.error}\n")
        return

    print(f"  → Confianza: {resultado.confidence_score:.0%}")
    print(f"  → Razonamiento: {resultado.raw_reasoning}\n")

    # Agrupar por ref
    grupos: dict = {}
    for comp in resultado.componentes:
        ref = getattr(comp, "ref", None) or "SIN-REF"
        grupos.setdefault(ref, []).append(comp)

    print(f"  → {len(resultado.componentes)} componentes en {len(grupos)} grupo(s):\n")

    for ref, comps in grupos.items():
        print(f"  ┌─ REF: {ref}  ({len(comps)} piezas)")
        for c in comps:
            print(f"  │  [{c.tipo}] {c.material} {c.acabado}  {c.ancho_cm}×{c.largo_cm}cm  ×{c.cantidad}")
        print(f"  └{'─'*50}")

    print()

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/Users/rvst/Desktop/Screenshot 2026-04-19 at 19.00.54.png"
    run_test(path)
