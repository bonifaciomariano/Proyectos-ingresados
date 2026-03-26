#!/usr/bin/env python3
"""
scraper_senado.py — Scraper automático del Senado de la Nación Argentina
=========================================================================
Obtiene todos los proyectos ingresados por Mesa de Entradas en los últimos
VENTANA_DIAS días, los cruza con Senadores_2026.xlsx para obtener bloques
políticos, y llama a generar_html.py para publicar el dashboard.

Uso manual:
    python scraper_senado.py

Variables de entorno opcionales:
    VENTANA_DIAS     Días hacia atrás a buscar (default: 30)
    EXCEL_SENADORES  Ruta al Excel de senadores (default: Senadores_2026.xlsx)
    ARCHIVO_SALIDA   Ruta del HTML a generar (default: index.html)
"""

import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: faltan dependencias. Ejecutá: pip install -r requirements.txt")
    sys.exit(1)

# ─────────────────────────────── Configuración ────────────────────────────────

FECHA_DESDE_FIJA = os.getenv("FECHA_DESDE", "")
VENTANA_DIAS     = int(os.getenv("VENTANA_DIAS", "30"))
EXCEL_SENADORES = os.getenv("EXCEL_SENADORES", "Senadores_2026.xlsx")
ARCHIVO_SALIDA  = os.getenv("ARCHIVO_SALIDA", "index.html")

BASE_URL       = "https://www.senado.gob.ar"
URL_BUSQUEDA   = f"{BASE_URL}/parlamentario/parlamentaria/"
URL_FECHA_MESA = f"{BASE_URL}/parlamentario/parlamentaria/fechaMesa"

# Tipos de expediente que nos interesan (los demás se descartan)
TIPOS_INCLUIR = {"PL", "PD", "PC", "PR", "CA", "AC", "CV"}

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaración",
    "PC": "Proyecto de Comunicación",
    "PR": "Proyecto de Resolución",
    "CA": "Comunicación Aprobada",
    "AC": "Acuerdo",
    "CV": "Convenio",
}

# Pausa entre requests al servidor (segundos)
PAUSA_ENTRE_REQUESTS = 1.0

# ─────────────────────────────── Logger ───────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────── Senadores ────────────────────────────────────

def cargar_senadores(excel_path):
    """
    Lee Senadores_2026.xlsx y devuelve un dict:
        {"APELLIDO, NOMBRE": "Nombre del Bloque"}
    """
    try:
        import openpyxl
    except ImportError:
        log.error("Falta openpyxl. Ejecutá: pip install openpyxl")
        return {}

    try:
        wb = openpyxl.load_workbook(excel_path)
    except FileNotFoundError:
        log.error(f"No se encontró '{excel_path}'")
        return {}
    except Exception as exc:
        log.error(f"Error abriendo '{excel_path}': {exc}")
        return {}

    ws = wb.active
    padron = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 3:
            continue
        bloque, apellido, nombre = row[0], row[1], row[2]
        if apellido and nombre:
            key = f"{apellido.strip()}, {nombre.strip()}".upper()
            padron[key] = bloque

    log.info(f"  → {len(padron)} senadores cargados desde '{excel_path}'")
    return padron


def normalizar_autor(nombre_sitio):
    """
    El sitio devuelve "Soria , Martin Ignacio" (espacio antes de la coma).
    Esta función lo convierte a "SORIA, MARTIN IGNACIO" para cruzar con el padrón.
    """
    if not nombre_sitio:
        return ""
    if "," not in nombre_sitio:
        return nombre_sitio.strip().upper()
    apellido, nombre = nombre_sitio.split(",", 1)
    return f"{apellido.strip()}, {nombre.strip()}".upper()


def get_bloques(autores_normalizados, senador_bloque):
    """Devuelve lista de bloques únicos para una lista de autores normalizados."""
    seen, result = set(), []
    for autor in autores_normalizados:
        bloque = senador_bloque.get(autor, "Sin datos")
        if bloque not in seen:
            seen.add(bloque)
            result.append(bloque)
    return result


# ─────────────────────────────── Scraping: búsqueda ──────────────────────────

def obtener_token(session):
    """Obtiene un CSRF token fresco de la página principal de búsqueda."""
    log.info("Obteniendo CSRF token...")
    resp = session.get(URL_BUSQUEDA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    inp = soup.find("input", {"name": "busqueda_proyectos[_token]"})
    if not inp:
        raise RuntimeError("No se encontró el campo busqueda_proyectos[_token] en la página")
    return inp["value"]


def parsear_tabla_resultados(html):
    """
    Extrae las filas de la tabla de resultados de una página de búsqueda.
    Devuelve lista de dicts con: nro, anio, tipo, origen, fecha, extracto, url.
    """
    soup = BeautifulSoup(html, "html.parser")
    tablas = soup.find_all("table")
    if not tablas:
        return []

    # La tabla con más filas es la de resultados
    tabla = max(tablas, key=lambda t: len(t.find_all("tr")))
    filas = []

    for tr in tabla.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue

        link = tds[0].find("a", href=True)
        if not link:
            continue

        exp_text = tds[0].get_text(strip=True)   # "158/26"
        url      = link["href"]
        if url and not url.startswith("http"):
            url = BASE_URL + url

        tipo     = tds[1].get_text(strip=True)
        origen   = tds[2].get_text(strip=True)
        fecha    = tds[4].get_text(strip=True)   # "13/03/2026"
        caratula = tds[5].get_text(strip=True)

        # Solo incluir tipos de interés
        if tipo not in TIPOS_INCLUIR:
            continue

        # Parsear nro/anio de "158/26"
        m = re.match(r"(\d+)/(\d+)", exp_text)
        if not m:
            continue
        nro      = int(m.group(1))
        anio_str = m.group(2)
        anio     = int("20" + anio_str) if len(anio_str) == 2 else int(anio_str)

        # Extracto = lo que sigue al primer ":"
        extracto = caratula
        if ":" in caratula:
            extracto = caratula[caratula.index(":") + 1:].strip()

        filas.append({
            "nro":      nro,
            "anio":     anio,
            "tipo":     tipo,
            "origen":   origen,
            "fecha":    fecha,
            "extracto": extracto,
            "url":      url,
        })

    return filas


def buscar_por_fechas(session, fecha_desde, fecha_hasta):
    """
    POST inicial + paginación GET.
    Devuelve lista completa de expedientes del período con los datos básicos.
    """
    token = obtener_token(session)

    payload = {
        "busqueda_proyectos[fechaDesdeMesa][day]":   str(fecha_desde.day),
        "busqueda_proyectos[fechaDesdeMesa][month]": str(fecha_desde.month),
        "busqueda_proyectos[fechaDesdeMesa][year]":  str(fecha_desde.year),
        "busqueda_proyectos[fechaHastaMesa][day]":   str(fecha_hasta.day),
        "busqueda_proyectos[fechaHastaMesa][month]": str(fecha_hasta.month),
        "busqueda_proyectos[fechaHastaMesa][year]":  str(fecha_hasta.year),
        "busqueda_proyectos[_token]":                token,
    }

    log.info(f"POST {URL_FECHA_MESA} | {fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}")
    resp = session.post(URL_FECHA_MESA, data=payload, timeout=30)
    resp.raise_for_status()

    todos  = []
    pagina = 1
    html   = resp.text

    while True:
        filas = parsear_tabla_resultados(html)
        log.info(f"  Página {pagina}: {len(filas)} expedientes de interés")
        todos.extend(filas)

        # Buscar link a la página siguiente
        soup      = BeautifulSoup(html, "html.parser")
        next_link = soup.find("a", href=re.compile(rf"[?&]page={pagina + 1}"))
        if not next_link:
            break

        pagina += 1
        url_sig = next_link["href"]
        if not url_sig.startswith("http"):
            url_sig = BASE_URL + url_sig

        time.sleep(PAUSA_ENTRE_REQUESTS)
        resp = session.get(url_sig, timeout=30)
        resp.raise_for_status()
        html = resp.text

    log.info(f"  → {len(todos)} expedientes en total")
    return todos


# ─────────────────────────────── Scraping: detalle ───────────────────────────

def obtener_detalle(session, url):
    """
    Visita la página de detalle de un expediente y extrae:
        autores_raw  : lista de strings "Apellido , Nombre"
        comisiones   : lista de strings con nombres de comisiones
        dae          : string con número de DAE (ej: "8/2026")

    Si ocurre cualquier error retorna campos vacíos sin interrumpir el flujo.
    """
    resultado = {"autores_raw": [], "comisiones": [], "dae": ""}
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Recolectar todas las filas de todas las tablas como listas de strings
        filas = []
        for tr in soup.select("table tr"):
            celdas = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
            texto  = " ".join(celdas).strip()
            if texto:
                filas.append(celdas)

        modo = None   # "autores" | "fechas" | "comisiones" | None

        for fila in filas:
            primer = fila[0] if fila else ""

            # ── Detectar sección ──────────────────────────────────────────
            if "Listado de Autores" in primer:
                modo = "autores"
                continue

            if "MESA DE ENTRADAS" in primer and "DADO CUENTA" in primer:
                modo = "fechas"
                continue

            if len(fila) >= 2 and "COMISI" in primer and "FECHA DE INGRESO" in fila[1]:
                modo = "comisiones"
                continue

            if "DIR. GRAL." in primer or "OBSERVACIONES" in primer:
                modo = None
                continue

            # ── Procesar según sección ────────────────────────────────────
            if modo == "autores":
                # Cada autor está en su propia fila de una celda
                if len(fila) == 1 and primer:
                    resultado["autores_raw"].append(primer)
                elif len(fila) > 1:
                    # Si hay más de una celda, salimos de la sección
                    modo = None

            elif modo == "fechas":
                # La siguiente fila tiene las fechas y el DAE
                if len(fila) >= 3 and re.match(r"\d", primer):
                    dae_raw = fila[2]
                    # "8/2026 Tipo: NORMAL" → "8/2026"
                    resultado["dae"] = dae_raw.split(" ")[0] if dae_raw else ""
                    modo = None

            elif modo == "comisiones":
                # "DE AGRICULTURA, GANADERÍA Y PESCA ORDEN DE GIRO: 1"
                if primer and "FECHA" not in primer:
                    com = re.sub(r"\s+ORDEN DE GIRO:\s*\d+.*$", "", primer).strip()
                    if com:
                        resultado["comisiones"].append(com)

    except Exception as exc:
        log.warning(f"    ⚠ Error en detalle {url}: {exc}")

    return resultado


# ─────────────────────────────── Main ─────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info(f"Scraper iniciado — ventana {VENTANA_DIAS} días")

    # 1. Cargar padrón de senadores
    senador_bloque = cargar_senadores(EXCEL_SENADORES)

    # 2. Definir rango de fechas
    hoy         = datetime.now()
    fecha_hasta = hoy
        if FECHA_DESDE_FIJA:
        try:
            fecha_desde = datetime.strptime(FECHA_DESDE_FIJA, "%d/%m/%Y")
            log.info(f"  Usando fecha de inicio fija: {FECHA_DESDE_FIJA}")
        except ValueError:
            log.error(f"  Formato de FECHA_DESDE inválido: '{FECHA_DESDE_FIJA}'. Usá DD/MM/YYYY")
            sys.exit(1)
    else:
        fecha_desde = hoy - timedelta(days=VENTANA_DIAS)


    # 3. Buscar expedientes
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })

    try:
        expedientes = buscar_por_fechas(session, fecha_desde, fecha_hasta)
    except Exception as exc:
        log.error(f"Error en la búsqueda principal: {exc}")
        sys.exit(1)

    if not expedientes:
        log.warning("No se encontraron expedientes en el período. Saliendo sin generar HTML.")
        sys.exit(0)

    # 4. Enriquecer cada expediente con datos del detalle
    proyectos = []
    total = len(expedientes)

    for i, exp in enumerate(expedientes, 1):
        log.info(f"  [{i:>3}/{total}] {exp['tipo']} {exp['nro']}/{exp['anio']}")

        time.sleep(PAUSA_ENTRE_REQUESTS)
        detalle = obtener_detalle(session, exp["url"]) if exp["url"] else {}

        # Normalizar nombres de autores y buscar bloques
        autores_raw        = detalle.get("autores_raw", [])
        autores_norm       = [normalizar_autor(a) for a in autores_raw if a.strip()]
        bloques            = get_bloques(autores_norm, senador_bloque)

        # Usar autores en formato "APELLIDO, NOMBRE" para display y filtro
        autores_display    = autores_norm if autores_norm else autores_raw

        proyectos.append({
            "nro":        exp["nro"],
            "anio":       exp["anio"],
            "tipo":       exp["tipo"],
            "tipo_label": TIPOS.get(exp["tipo"], exp["tipo"]),
            "extracto":   exp["extracto"],
            "autores":    autores_display,
            "bloques":    bloques,
            "comisiones": detalle.get("comisiones", []),
            "fecha":      exp["fecha"],
            "dae":        detalle.get("dae", ""),
            "origen":     exp["origen"],
            "url":        exp["url"],
        })

    log.info(f"  → {len(proyectos)} proyectos procesados")

    # 5. Generar dashboard HTML
    titulo      = f"Últimos {VENTANA_DIAS} días · Actualizado {hoy.strftime('%d/%m/%Y')}"
    fecha_datos = hoy.strftime("%d/%m/%Y")

    try:
        from generar_html import generar_desde_lista
        generar_desde_lista(proyectos, titulo, fecha_datos, ARCHIVO_SALIDA)
        log.info(f"  → Dashboard generado: {ARCHIVO_SALIDA}")
    except Exception as exc:
        log.error(f"Error generando HTML: {exc}")
        sys.exit(1)

    log.info("Scraper finalizado con éxito.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
