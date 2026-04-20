#!/usr/bin/env python3
"""
scraper_historico.py — Scraper de expedientes históricos (2010-2024)
====================================================================
Lee scraping_historico.json, scrapea la mitad del año que corresponde,
actualiza trazabilidad_historico.tsv y avanza el archivo de control.

Cada mitad de año es una corrida independiente. Si el tiempo se agota,
el progreso queda guardado en el TSV y se retoma en la próxima corrida.

Variables de entorno:
    ARCHIVO_HIST_TSV    TSV de salida (default: trazabilidad_historico.tsv)
    HISTORICO_CONTROL   JSON de control (default: scraping_historico.json)
    TIMEOUT_MINUTOS     Minutos máximos de ejecución (default: 20)
"""

import csv
import json
import logging
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: pip install -r requirements.txt")
    sys.exit(1)

from scraper_senado import (
    buscar_por_fechas,
    obtener_detalle,
    normalizar_autor,
    clasificar_autores,
    construir_url_expediente,
    PAUSA_ENTRE_REQUESTS,
    TIPOS,
)

# ─────────────────────────────── Configuración ────────────────────────────────

ARCHIVO_HIST_TSV  = os.getenv("ARCHIVO_HIST_TSV",  "trazabilidad_historico.tsv")
HISTORICO_CONTROL = os.getenv("HISTORICO_CONTROL", "scraping_historico.json")
TIMEOUT_MINUTOS   = int(os.getenv("TIMEOUT_MINUTOS", "20"))
ANIO_INICIO       = 2010

TSV_FIELDNAMES = ["NRO", "ANIO", "TIPO", "ORIGEN", "CARATULA", "MESA", "DAE",
                  "AUTOR", "COM1", "COM2", "COM3", "COM4", "COM5"]

# ─────────────────────────────── Logger ───────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─────────────────────────────── Control ──────────────────────────────────────

def leer_control():
    if not os.path.exists(HISTORICO_CONTROL):
        return {
            "ultimo_anio_completado": None,
            "en_progreso": {"anio": 2024, "mitad": 1},
            "activo": True,
        }
    with open(HISTORICO_CONTROL, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_control(estado):
    with open(HISTORICO_CONTROL, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    log.info(f"  → Control guardado: {estado}")


def avanzar_control(estado):
    """Cierra la mitad actual y avanza al siguiente año/mitad."""
    ep = estado["en_progreso"]
    if ep["mitad"] == 1:
        ep["mitad"] = 2
    else:
        anio_completo = ep["anio"]
        estado["ultimo_anio_completado"] = anio_completo
        log.info(f"  → Año {anio_completo} completado.")
        siguiente = anio_completo - 1
        if siguiente < ANIO_INICIO:
            estado["activo"] = False
            estado["en_progreso"] = None
            log.info("  → Scraping histórico completado hasta 2010. Desactivando.")
        else:
            estado["en_progreso"] = {"anio": siguiente, "mitad": 1}
    return estado

# ─────────────────────────────── TSV ──────────────────────────────────────────

def cargar_claves_existentes():
    claves = set()
    if not os.path.exists(ARCHIVO_HIST_TSV):
        return claves
    with open(ARCHIVO_HIST_TSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                claves.add((int(row["NRO"]), int(row["ANIO"]), row["TIPO"].strip()))
            except (ValueError, KeyError):
                pass
    return claves


def agregar_al_tsv(filas):
    existe = os.path.exists(ARCHIVO_HIST_TSV)
    with open(ARCHIVO_HIST_TSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_FIELDNAMES, delimiter="\t",
                                extrasaction="ignore")
        if not existe:
            writer.writeheader()
        writer.writerows(filas)

# ─────────────────────────────── Main ─────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("Scraper histórico iniciado")

    estado = leer_control()
    if not estado.get("activo", True):
        log.info("Scraping histórico inactivo (completado hasta 2010). Saliendo.")
        return

    ep = estado.get("en_progreso")
    if not ep:
        log.info("Sin año en progreso. Saliendo.")
        return

    anio  = ep["anio"]
    mitad = ep["mitad"]
    log.info(f"Procesando: año {anio}, mitad {mitad}")

    if mitad == 1:
        fecha_desde = datetime(anio, 1, 1)
        fecha_hasta = datetime(anio, 6, 30)
    else:
        fecha_desde = datetime(anio, 7, 1)
        fecha_hasta = datetime(anio, 12, 31)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    })

    claves_existentes = cargar_claves_existentes()
    log.info(f"  → {len(claves_existentes)} expedientes ya en TSV histórico")

    try:
        expedientes = buscar_por_fechas(session, fecha_desde, fecha_hasta)
    except Exception as exc:
        log.error(f"Error en búsqueda histórica: {exc}")
        return

    pendientes = [e for e in expedientes
                  if (e["nro"], e["anio"], e["tipo"]) not in claves_existentes]
    log.info(f"  → {len(expedientes)} encontrados, {len(pendientes)} pendientes de procesar")

    inicio = time.time()
    timeout_seg = TIMEOUT_MINUTOS * 60 - 60  # 1 min de margen para guardar
    nuevos = 0
    descartados = 0
    filas_nuevas = []
    mitad_completa = True

    for i, exp in enumerate(pendientes, 1):
        elapsed = time.time() - inicio
        if elapsed > timeout_seg:
            log.warning(f"  Timeout ({TIMEOUT_MINUTOS} min). Procesados {i-1}/{len(pendientes)}. "
                        f"Se retoma en la próxima corrida.")
            mitad_completa = False
            break

        log.info(f"  [{i:>3}/{len(pendientes)}] {exp['tipo']} {exp['nro']}/{exp['anio']}")
        time.sleep(PAUSA_ENTRE_REQUESTS)
        detalle = obtener_detalle(session, exp["url"]) if exp["url"] else {}

        if detalle.get("descartar"):
            descartados += 1
            continue

        autores_raw  = detalle.get("autores_raw", [])
        autores_norm = [normalizar_autor(a) for a in autores_raw if a.strip()]
        caratula = exp.get("caratula", exp["extracto"])
        autores, _ = clasificar_autores(caratula, autores_norm)

        coms = detalle.get("comisiones", [])
        fila = {
            "NRO":    exp["nro"],
            "ANIO":   exp["anio"],
            "TIPO":   exp["tipo"],
            "ORIGEN": exp["origen"],
            "CARATULA": caratula,
            "MESA":   exp["fecha"],
            "DAE":    detalle.get("dae", ""),
            "AUTOR":  " - ".join(autores),
            "COM1":   coms[0] if len(coms) > 0 else "",
            "COM2":   coms[1] if len(coms) > 1 else "",
            "COM3":   coms[2] if len(coms) > 2 else "",
            "COM4":   coms[3] if len(coms) > 3 else "",
            "COM5":   coms[4] if len(coms) > 4 else "",
        }
        filas_nuevas.append(fila)
        claves_existentes.add((exp["nro"], exp["anio"], exp["tipo"]))
        nuevos += 1

    if filas_nuevas:
        agregar_al_tsv(filas_nuevas)
        log.info(f"  → {nuevos} expedientes nuevos agregados al TSV histórico")

    log.info(f"  → {descartados} descartados (sancionados/archivados/caducados)")

    if mitad_completa:
        estado = avanzar_control(estado)

    guardar_control(estado)
    log.info("Scraper histórico finalizado.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
