#!/usr/bin/env python3
"""
generar_embeddings.py — Genera embeddings semánticos para proyectos legislativos
=================================================================================
Lee proyectos desde trazabilidad.tsv, genera vectores con el modelo
intfloat/multilingual-e5-small (via fastembed, sin PyTorch) y los guarda
en embeddings.json. Solo procesa proyectos que aún no tienen vector.

El modelo es compatible con Xenova/multilingual-e5-small en Transformers.js,
por lo que la búsqueda semántica en el browser no requiere ninguna API key.

Variables de entorno:
    ARCHIVO_HISTORICOS   TSV de entrada (default: trazabilidad.tsv)
    EMBEDDINGS_PATH      JSON de salida (default: embeddings.json)
"""

import csv
import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

ARCHIVO_HISTORICOS = os.getenv("ARCHIVO_HISTORICOS", "trazabilidad.tsv")
EMBEDDINGS_PATH    = os.getenv("EMBEDDINGS_PATH", "embeddings.json")
MODEL_NAME         = "intfloat/multilingual-e5-small"

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaración",
    "PC": "Proyecto de Comunicación",
    "PR": "Proyecto de Resolución",
    "CA": "Com. de Auditoría",
    "AC": "Acuerdo",
    "CV": "Com. Varias",
}


# ─────────────────────────────── Lectura del TSV ─────────────────────────────

def leer_proyectos_tsv(tsv_path):
    """Lee trazabilidad.tsv y devuelve lista de dicts con los campos relevantes."""
    if not os.path.exists(tsv_path):
        log.error(f"No se encontró '{tsv_path}'")
        return []

    proyectos = []
    with open(tsv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            nro_str = (row.get("NRO") or "").strip()
            if not nro_str:
                continue

            nro    = nro_str
            anio   = (row.get("ANIO") or "2025").strip()
            tipo   = (row.get("TIPO") or "PL").strip()
            origen = (row.get("ORIGEN") or "S").strip()

            caratula = (row.get("CARATULA") or "").strip()
            extracto = caratula
            if ":" in caratula:
                extracto = caratula[caratula.index(":") + 1:].strip()

            # Extraer apellidos de autores (el TSV no tiene bloques: se omiten)
            autor_raw = (row.get("AUTOR") or "").strip()
            autores = []
            if autor_raw:
                for a in autor_raw.split(" - "):
                    a = a.strip().rstrip("-").strip()
                    if a:
                        apellido = a.split(",")[0].strip() if "," in a else a
                        autores.append(apellido)

            comisiones = []
            for i in range(1, 6):
                com = (row.get(f"COM{i}") or "").strip()
                if com:
                    comisiones.append(com)

            proyectos.append({
                "key":        f"{nro}-{anio}-{tipo}",
                "extracto":   extracto,
                "autores":    autores,
                "comisiones": comisiones,
                "origen":     origen,
                "tipo_label": TIPOS.get(tipo, tipo),
            })

    log.info(f"  → {len(proyectos)} proyectos leídos de '{tsv_path}'")
    return proyectos


# ─────────────────────────────── Texto a embeddear ───────────────────────────

def construir_texto(p):
    """Concatena los campos de un proyecto en un único string para embeddear."""
    partes = [p["extracto"]]
    if p["autores"]:
        partes.append(" ".join(p["autores"]))
    if p["comisiones"]:
        partes.append(" ".join(p["comisiones"]))
    if p["origen"]:
        partes.append(p["origen"])
    if p["tipo_label"]:
        partes.append(p["tipo_label"])
    return " ".join(filter(None, partes))


# ─────────────────────────────── Main ────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("Generador de embeddings iniciado")

    # 1. Leer proyectos del TSV
    proyectos = leer_proyectos_tsv(ARCHIVO_HISTORICOS)
    if not proyectos:
        log.info("Sin proyectos para procesar. Saliendo.")
        return

    # 2. Cargar embeddings existentes (si hay)
    embeddings_existentes = {}
    if os.path.exists(EMBEDDINGS_PATH):
        try:
            with open(EMBEDDINGS_PATH, "r", encoding="utf-8") as f:
                embeddings_existentes = json.load(f)
            log.info(f"  → {len(embeddings_existentes)} embeddings existentes cargados")
        except Exception as exc:
            log.warning(f"  No se pudo leer '{EMBEDDINGS_PATH}': {exc}. Se recalculará todo.")
            embeddings_existentes = {}

    # 3. Determinar proyectos nuevos
    nuevos = [p for p in proyectos if p["key"] not in embeddings_existentes]
    log.info(f"  → {len(nuevos)} proyectos nuevos sin embedding")

    if not nuevos:
        log.info("Nada nuevo. Saliendo sin modificar embeddings.json.")
        return

    # 4. Cargar modelo (fastembed usa ONNX runtime, sin PyTorch)
    try:
        from fastembed import TextEmbedding
    except ImportError:
        log.error("fastembed no está instalado. Ejecutá: pip install fastembed")
        sys.exit(1)

    log.info(f"Cargando modelo '{MODEL_NAME}'...")
    try:
        model = TextEmbedding(model_name=MODEL_NAME)
    except Exception as exc:
        log.error(f"Error cargando el modelo: {exc}")
        log.info("Saliendo sin modificar embeddings.json.")
        return

    # 5. Generar embeddings
    # fastembed.passage_embed() agrega automáticamente el prefijo "passage: "
    # requerido por multilingual-e5, compatible con "query: " en Transformers.js
    textos = [construir_texto(p) for p in nuevos]
    keys   = [p["key"] for p in nuevos]

    log.info(f"Generando embeddings para {len(nuevos)} proyectos...")
    try:
        vectores = list(model.passage_embed(textos))
    except Exception as exc:
        log.error(f"Error generando embeddings: {exc}")
        log.info("Saliendo sin modificar embeddings.json.")
        return

    # 6. Agregar al dict existente
    for key, vec in zip(keys, vectores):
        embeddings_existentes[key] = vec.tolist()

    log.info(f"  → {len(nuevos)} embeddings nuevos generados")

    # 7. Guardar (compact JSON para reducir tamaño en disco y en fetch)
    try:
        with open(EMBEDDINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(embeddings_existentes, f, ensure_ascii=False, separators=(",", ":"))
        log.info(f"  → Guardado en '{EMBEDDINGS_PATH}' ({os.path.getsize(EMBEDDINGS_PATH):,} bytes)")
    except Exception as exc:
        log.error(f"Error guardando '{EMBEDDINGS_PATH}': {exc}")
        return

    log.info("Generador de embeddings finalizado con éxito.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
