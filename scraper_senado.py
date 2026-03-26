#!/usr/bin/env python3
"""
scraper_senado.py
Obtiene proyectos ingresados por Mesa de Entradas y genera el dashboard.

Variables de entorno:
    FECHA_DESDE      Fecha de inicio fija DD/MM/YYYY (ej: 01/03/2026)
    VENTANA_DIAS     Dias hacia atras si no hay FECHA_DESDE (default: 30)
    EXCEL_SENADORES  Excel de senadores (default: Senadores_2026.xlsx)
    ARCHIVO_SALIDA   HTML a generar (default: index.html)
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
    print("ERROR: faltan dependencias. Ejecuta: pip install -r requirements.txt")
    sys.exit(1)

FECHA_DESDE_FIJA = os.getenv("FECHA_DESDE", "")
VENTANA_DIAS     = int(os.getenv("VENTANA_DIAS", "30"))
EXCEL_SENADORES  = os.getenv("EXCEL_SENADORES", "Senadores_2026.xlsx")
ARCHIVO_SALIDA   = os.getenv("ARCHIVO_SALIDA", "index.html")

BASE_URL       = "https://www.senado.gob.ar"
URL_BUSQUEDA   = f"{BASE_URL}/parlamentario/parlamentaria/"
URL_FECHA_MESA = f"{BASE_URL}/parlamentario/parlamentaria/fechaMesa"

TIPOS_INCLUIR = {"PL", "PD", "PC", "PR", "CA", "AC", "CV"}

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaracion",
    "PC": "Proyecto de Comunicacion",
    "PR": "Proyecto de Resolucion",
    "CA": "Comunicacion Aprobada",
    "AC": "Acuerdo",
    "CV": "Convenio",
}

PAUSA_ENTRE_REQUESTS = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def cargar_senadores(excel_path):
    try:
        import openpyxl
    except ImportError:
        log.error("Falta openpyxl.")
        return {}
    try:
        wb = openpyxl.load_workbook(excel_path)
    except FileNotFoundError:
        log.error(f"No se encontro '{excel_path}'")
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
    log.info(f"  {len(padron)} senadores cargados desde '{excel_path}'")
    return padron


def normalizar_autor(nombre_sitio):
    if not nombre_sitio:
        return ""
    if "," not in nombre_sitio:
        return nombre_sitio.strip().upper()
    apellido, nombre = nombre_sitio.split(",", 1)
    return f"{apellido.strip()}, {nombre.strip()}".upper()


def get_bloques(autores_normalizados, senador_bloque):
    seen, result = set(), []
    for autor in autores_normalizados:
        bloque = senador_bloque.get(autor, "Sin datos")
        if bloque not in seen:
            seen.add(bloque)
            result.append(bloque)
    return result


def obtener_token(session):
    log.info("Obteniendo CSRF token...")
    resp = session.get(URL_BUSQUEDA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    inp = soup.find("input", {"name": "busqueda_proyectos[_token]"})
    if not inp:
        raise RuntimeError("No se encontro el campo _token en la pagina")
    return inp["value"]


def parsear_tabla_resultados(html):
    soup = BeautifulSoup(html, "html.parser")
    tablas = soup.find_all("table")
    if not tablas:
        return []
    tabla = max(tablas, key=lambda t: len(t.find_all("tr")))
    filas = []
    for tr in tabla.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        link = tds[0].find("a", href=True)
        if not link:
            continue
        exp_text = tds[0].get_text(strip=True)
        url      = link["href"]
        if url and not url.startswith("http"):
            url = BASE_URL + url
        tipo     = tds[1].get_text(strip=True)
        origen   = tds[2].get_text(strip=True)
        fecha    = tds[4].get_text(strip=True)
        caratula = tds[5].get_text(strip=True)
        if tipo not in TIPOS_INCLUIR:
            continue
        m = re.match(r"(\d+)/(\d+)", exp_text)
        if not m:
            continue
        nro      = int(m.group(1))
        anio_str = m.group(2)
        anio     = int("20" + anio_str) if len(anio_str) == 2 else int(anio_str)
        extracto = caratula
        if ":" in caratula:
            extracto = caratula[caratula.index(":") + 1:].strip()
        filas.append({
            "nro": nro, "anio": anio, "tipo": tipo, "origen": origen,
            "fecha": fecha, "extracto": extracto, "url": url,
        })
    return filas


def buscar_por_fechas(session, fecha_desde, fecha_hasta):
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
    log.info(f"Buscando del {fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}")
    resp = session.post(URL_FECHA_MESA, data=payload, timeout=30)
    resp.raise_for_status()
    todos  = []
    pagina = 1
    html   = resp.text
    while True:
        filas = parsear_tabla_resultados(html)
        log.info(f"  Pagina {pagina}: {len(filas)} expedientes")
        todos.extend(filas)
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
    log.info(f"  Total: {len(todos)} expedientes")
    return todos


def obtener_detalle(session, url):
    resultado = {"autores_raw": [], "comisiones": [], "dae": ""}
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        filas = []
        for tr in soup.select("table tr"):
            celdas = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
            texto  = " ".join(celdas).strip()
            if texto:
                filas.append(celdas)
        modo = None
        for fila in filas:
            primer = fila[0] if fila else ""
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
            if modo == "autores":
                if len(fila) == 1 and primer:
                    resultado["autores_raw"].append(primer)
                elif len(fila) > 1:
                    modo = None
            elif modo == "fechas":
                if len(fila) >= 3 and re.match(r"\d", primer):
                    dae_raw = fila[2]
                    resultado["dae"] = dae_raw.split(" ")[0] if dae_raw else ""
                    modo = None
            elif modo == "comisiones":
                if primer and "FECHA" not in primer:
                    com = re.sub(r"\s+ORDEN DE GIRO:\s*\d+.*$", "", primer).strip()
                    if com:
                        resultado["comisiones"].append(com)
    except Exception as exc:
        log.warning(f"Error en detalle {url}: {exc}")
    return resultado


def main():
    log.info("=" * 60)
    log.info(f"Scraper iniciado")

    senador_bloque = cargar_senadores(EXCEL_SENADORES)

    hoy         = datetime.now()
    fecha_hasta = hoy

    if FECHA_DESDE_FIJA:
        try:
            fecha_desde = datetime.strptime(FECHA_DESDE_FIJA, "%d/%m/%Y")
            log.info(f"  Fecha de inicio fija: {FECHA_DESDE_FIJA}")
        except ValueError:
            log.error(f"  Formato invalido en FECHA_DESDE: '{FECHA_DESDE_FIJA}'. Usar DD/MM/YYYY")
            sys.exit(1)
    else:
        fecha_desde = hoy - timedelta(days=VENTANA_DIAS)

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
        log.error(f"Error en la busqueda: {exc}")
        sys.exit(1)

    if not expedientes:
        log.warning("No se encontraron expedientes. Saliendo sin generar HTML.")
        sys.exit(0)

    proyectos = []
    total = len(expedientes)

    for i, exp in enumerate(expedientes, 1):
        log.info(f"  [{i:>3}/{total}] {exp['tipo']} {exp['nro']}/{exp['anio']}")
        time.sleep(PAUSA_ENTRE_REQUESTS)
        detalle        = obtener_detalle(session, exp["url"]) if exp["url"] else {}
        autores_raw    = detalle.get("autores_raw", [])
        autores_norm   = [normalizar_autor(a) for a in autores_raw if a.strip()]
        bloques        = get_bloques(autores_norm, senador_bloque)
        autores_display = autores_norm if autores_norm else autores_raw
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

    log.info(f"  {len(proyectos)} proyectos procesados")

    titulo      = f"Desde 01/03/2026 - Actualizado {hoy.strftime('%d/%m/%Y')}"
    fecha_datos = hoy.strftime("%d/%m/%Y")

    try:
        from generar_html import generar_desde_lista
        generar_desde_lista(proyectos, titulo, fecha_datos, ARCHIVO_SALIDA)
        log.info(f"  Dashboard generado: {ARCHIVO_SALIDA}")
    except Exception as exc:
        log.error(f"Error generando HTML: {exc}")
        sys.exit(1)

    log.info("Scraper finalizado con exito.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
