#!/usr/bin/env python3
"""
scraper_senado.py — Scraper automático del Senado de la Nación Argentina
=========================================================================
Obtiene proyectos ingresados por Mesa de Entradas, obtiene bloques políticos
y provincias desde la web, carga proyectos históricos de trazabilidad.tsv si
existe, clasifica autores vs coautores, y genera el dashboard HTML.

Variables de entorno opcionales:
    FECHA_DESDE      Fecha de inicio fija DD/MM/YYYY. Si se define, ignora VENTANA_DIAS.
    VENTANA_DIAS     Días hacia atrás (default: 30).
    ARCHIVO_SALIDA   HTML a generar (default: index.html).
"""

import csv
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
ARCHIVO_SALIDA   = os.getenv("ARCHIVO_SALIDA", "index.html")
ARCHIVO_HISTORICOS = os.getenv("ARCHIVO_HISTORICOS", "trazabilidad.tsv")

BASE_URL       = "https://www.senado.gob.ar"
URL_BUSQUEDA   = f"{BASE_URL}/parlamentario/parlamentaria/"
URL_FECHA_MESA = f"{BASE_URL}/parlamentario/parlamentaria/fechaMesa"
URL_SENADORES_ALFA   = f"{BASE_URL}/senadores/listados/listaSenadoRes"
URL_SENADORES_BLOQUE = f"{BASE_URL}/senadores/listados/agrupados-por-bloques"

TIPOS_INCLUIR = {"PL", "PD", "PC", "PR", "CA", "AC", "CV"}

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaración",
    "PC": "Proyecto de Comunicación",
    "PR": "Proyecto de Resolución",
    "CA": "Com. de Auditoría",
    "AC": "Acuerdo",
    "CV": "Com. Varias",
}

PAUSA_ENTRE_REQUESTS = 1.0

# ─────────── Senadores 2025 (mandatos terminados) — fallback ─────────────────

SENADORES_2025 = {
    "PILATTI VERGARA": {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "CHACO"},
    "RODAS":           {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "CHACO"},
    "ZIMMERMANN":      {"bloque": "UNIÓN CÍVICA RADICAL",      "provincia": "CHACO"},
    "RECALDE":         {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "CABA"},
    "TAGLIAFERRI":     {"bloque": "FRENTE PRO",                "provincia": "CABA"},
    "LOUSTEAU":        {"bloque": "UNIÓN CÍVICA RADICAL",      "provincia": "CABA"},
    "CORA":            {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "ENTRE RÍOS"},
    "DE ANGELI":       {"bloque": "FRENTE PRO",                "provincia": "ENTRE RÍOS"},
    "OLALLA":          {"bloque": "UNIÓN CÍVICA RADICAL",      "provincia": "ENTRE RÍOS"},
    "CREXELL":         {"bloque": "MOVIMIENTO NEUQUINO",       "provincia": "NEUQUÉN"},
    "PARRILLI":        {"bloque": "UNIDAD CIUDADANA",          "provincia": "NEUQUÉN"},
    "SAPAG":           {"bloque": "UNIDAD CIUDADANA",          "provincia": "NEUQUÉN"},
    "SILVA":           {"bloque": "JUNTOS SOMOS RÍO NEGRO",    "provincia": "RÍO NEGRO"},
    "DOÑATE":          {"bloque": "UNIDAD CIUDADANA",          "provincia": "RÍO NEGRO"},
    "GARCÍA LARRABURU":{"bloque": "UNIDAD CIUDADANA",          "provincia": "RÍO NEGRO"},
    "ROMERO":          {"bloque": "CAMBIO FEDERAL",            "provincia": "SALTA"},
    "GIMÉNEZ":         {"bloque": "UNIDAD CIUDADANA",          "provincia": "SALTA"},
    "LEAVY":           {"bloque": "UNIDAD CIUDADANA",          "provincia": "SALTA"},
    "LEDESMA ABDALA DE ZAMORA": {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "SANTIAGO DEL ESTERO"},
    "MONTENEGRO":      {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "SANTIAGO DEL ESTERO"},
    "NEDER":           {"bloque": "FRENTE NACIONAL Y POPULAR", "provincia": "SANTIAGO DEL ESTERO"},
    "DURÉ":            {"bloque": "UNIDAD CIUDADANA",          "provincia": "TIERRA DEL FUEGO"},
    "LÓPEZ":           {"bloque": "UNIDAD CIUDADANA",          "provincia": "TIERRA DEL FUEGO"},
    "BLANCO":          {"bloque": "UNIÓN CÍVICA RADICAL",      "provincia": "TIERRA DEL FUEGO"},
}

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


# ─────────────────────────────── Helpers ─────────────────────────────────────

def normalizar_autor(nombre_sitio):
    if not nombre_sitio:
        return ""
    if "," not in nombre_sitio:
        return nombre_sitio.strip().upper()
    apellido, nombre = nombre_sitio.split(",", 1)
    return f"{apellido.strip()}, {nombre.strip()}".upper()


def buscar_info(nombre_norm, senador_info):
    """Busca bloque y provincia de un senador, con fallback a SENADORES_2025."""
    if nombre_norm in senador_info:
        return senador_info[nombre_norm]
    apellido = nombre_norm.split(",")[0].strip() if "," in nombre_norm else nombre_norm.strip()
    if apellido in SENADORES_2025:
        return SENADORES_2025[apellido]
    return {"bloque": "Sin datos", "provincia": ""}


def get_bloques(autores_normalizados, senador_info):
    seen, result = set(), []
    for autor in autores_normalizados:
        bloque = buscar_info(autor, senador_info)["bloque"]
        if bloque not in seen:
            seen.add(bloque)
            result.append(bloque)
    return result


def get_provincias(autores_normalizados, senador_info):
    seen, result = set(), []
    for autor in autores_normalizados:
        prov = buscar_info(autor, senador_info)["provincia"]
        if prov and prov not in seen:
            seen.add(prov)
            result.append(prov)
    return result


def clasificar_autores(extracto, autores_detalle):
    """Separa autores principales de coautores según 'Y OTROS' en el extracto."""
    if not autores_detalle:
        return [], []

    atrib = extracto.split(":")[0].upper() if ":" in extracto else extracto.upper()
    tiene_y_otros = bool(re.search(r'\bY\s+OTR[OA]S?\b', atrib))

    if not tiene_y_otros:
        return autores_detalle, []

    atrib_limpio = re.sub(r'\s*\bY\s+OTR[OA]S?\b', '', atrib).strip()
    partes = re.split(r'[,]\s*|\s+Y\s+', atrib_limpio)
    apellidos_extracto = [p.strip() for p in partes if p.strip()]

    autores, coautores = [], []
    for autor in autores_detalle:
        apellido = autor.split(",")[0].strip().upper()
        es_principal = any(ap in apellido or apellido in ap for ap in apellidos_extracto)
        if es_principal:
            autores.append(autor)
        else:
            coautores.append(autor)

    if not autores and autores_detalle:
        autores = [autores_detalle[0]]
        coautores = autores_detalle[1:]

    return autores, coautores


def construir_url_expediente(nro, anio, origen, tipo):
    anio_short = str(anio)[-2:]
    return f"{BASE_URL}/parlamentario/comisiones/verExp/{nro}.{anio_short}/{origen}/{tipo}"


# ─────────────────────────────── Senadores (web) ─────────────────────────────

def scraper_senadores_web(session):
    """Devuelve {nombre_normalizado: {"bloque": str, "provincia": str}}"""
    log.info("Scraping senadores desde la web del Senado...")

    # 1) Lista alfabética → nombres + IDs + provincia (columna "Distrito")
    nombres = {}
    provincia_por_id = {}
    try:
        resp = session.get(URL_SENADORES_ALFA, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tr in soup.select("table tr"):
            link = tr.select_one("a[href*='/senadores/senador/']")
            if not link:
                continue
            href = link.get("href", "")
            m = re.search(r"/senadores/senador/(\d+)", href)
            if not m:
                continue
            sid = m.group(1)
            name = link.get_text(strip=True)
            if "," in name and sid not in nombres:
                nombres[sid] = normalizar_autor(name)
            # Extraer provincia de la columna "Distrito" (3ra columna, índice 2)
            tds = tr.find_all("td")
            if len(tds) >= 3 and sid not in provincia_por_id:
                prov = tds[2].get_text(strip=True)
                if prov:
                    provincia_por_id[sid] = prov
        log.info(f"  → {len(nombres)} senadores en lista alfabética, {len(provincia_por_id)} con provincia")
    except Exception as exc:
        log.error(f"  Error obteniendo lista alfabética: {exc}")
        return {}

    time.sleep(0.5)

    # 2) Bloques → bloque por ID
    bloques_por_id = {}
    try:
        resp = session.get(URL_SENADORES_BLOQUE, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        current_bloque = None
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            primera = tds[0]
            links_en_primera = primera.select("a[href*='/senadores/senador/']")
            if not links_en_primera:
                texto = primera.get_text(strip=True)
                if texto and texto.lower() not in ("bloque", "presidente/a",
                    "integrantes", "contacto", ""):
                    current_bloque = texto
            for link in tr.select("a[href*='/senadores/senador/']"):
                href = link.get("href", "")
                m = re.search(r"/senadores/senador/(\d+)", href)
                if m and current_bloque:
                    bloques_por_id[m.group(1)] = current_bloque
        log.info(f"  → {len(bloques_por_id)} senadores en página de bloques")
    except Exception as exc:
        log.error(f"  Error obteniendo bloques: {exc}")
        return {}

    # 3) Combinar
    padron = {}
    for sid, nombre_norm in nombres.items():
        padron[nombre_norm] = {
            "bloque":    bloques_por_id.get(sid, "Sin datos"),
            "provincia": provincia_por_id.get(sid, ""),
        }

    con_bloque = sum(1 for v in padron.values() if v["bloque"] != "Sin datos")
    con_prov   = sum(1 for v in padron.values() if v["provincia"])
    log.info(f"  → {len(padron)} senadores totales, {con_bloque} con bloque, {con_prov} con provincia")
    return padron


# ─────────────────────────────── Históricos (TSV) ────────────────────────────

def cargar_historicos(tsv_path, senador_info):
    """Carga proyectos históricos desde trazabilidad.tsv"""
    if not os.path.exists(tsv_path):
        log.info(f"  No se encontró '{tsv_path}', sin históricos.")
        return []

    log.info(f"Cargando proyectos históricos desde '{tsv_path}'...")
    proyectos = []

    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            nro_str = (row.get("NRO") or "").strip()
            if not nro_str:
                continue

            nro    = int(nro_str)
            anio   = int(row.get("ANIO", "2025").strip() or "2025")
            tipo   = (row.get("TIPO") or "PL").strip()
            origen = (row.get("ORIGEN") or "S").strip()

            caratula = (row.get("CARATULA") or "").strip()
            extracto = caratula
            if ":" in caratula:
                extracto = caratula[caratula.index(":") + 1:].strip()

            mesa_raw = (row.get("MESA") or "").strip()
            fecha = ""
            fecha_match = re.search(r"(\d{2}/\d{2}/\d{4})", mesa_raw)
            if fecha_match:
                fecha = fecha_match.group(1)

            dae_raw = (row.get("DAE") or "").strip()
            dae = ""
            dae_match = re.match(r"(\d+)", dae_raw)
            if dae_match:
                anio_dae_match = re.search(r"(\d{4})", dae_raw)
                if anio_dae_match:
                    dae = f"{dae_match.group(1)}/{anio_dae_match.group(1)}"

            autor_raw = (row.get("AUTOR") or "").strip()
            todos_autores = []
            if autor_raw:
                for a in autor_raw.split(" - "):
                    a = a.strip().rstrip("-").strip()
                    if a:
                        todos_autores.append(normalizar_autor(a))

            autores, coautores = clasificar_autores(caratula, todos_autores)
            bloques     = get_bloques(autores, senador_info)
            provincias  = get_provincias(autores, senador_info)

            comisiones = []
            for i in range(1, 6):
                com = (row.get(f"COM{i}") or "").strip()
                if com:
                    comisiones.append(com)

            url = construir_url_expediente(nro, anio, origen, tipo)

            proyectos.append({
                "nro":        nro,
                "anio":       anio,
                "tipo":       tipo,
                "tipo_label": TIPOS.get(tipo, tipo),
                "extracto":   extracto,
                "autores":    autores,
                "coautores":  coautores,
                "bloques":    bloques,
                "provincias": provincias,
                "comisiones": comisiones,
                "fecha":      fecha,
                "dae":        dae,
                "origen":     origen,
                "url":        url,
            })

    log.info(f"  → {len(proyectos)} proyectos históricos cargados")
    return proyectos


# ─────────────────────────────── Scraping: búsqueda ──────────────────────────

def obtener_token(session):
    log.info("Obteniendo CSRF token...")
    resp = session.get(URL_BUSQUEDA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    inp = soup.find("input", {"name": "busqueda_proyectos[_token]"})
    if not inp:
        raise RuntimeError("No se encontró el campo busqueda_proyectos[_token]")
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
            "caratula": caratula,
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
    resultado = {"autores_raw": [], "comisiones": [], "dae": ""}
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for link in soup.select("a[href*='/senadores/senador/']"):
            title = link.get("title", "").strip()
            texto = link.get_text(strip=True)
            nombre = title if title else texto
            if nombre:
                resultado["autores_raw"].append(nombre)

        for tr in soup.select("table tr"):
            texto_fila = tr.get_text(" ", strip=True)
            if "ORDEN DE GIRO" in texto_fila:
                primera_celda = tr.find("td")
                if primera_celda:
                    com_text = primera_celda.get_text(strip=True)
                    com = re.sub(r"\s*ORDEN DE GIRO:\s*\d+.*$", "", com_text).strip()
                    if com:
                        resultado["comisiones"].append(com)

        texto_completo = soup.get_text()
        dae_match = re.search(r"D\.A\.E\.\s*(\d+/\d{4})", texto_completo)
        if dae_match:
            resultado["dae"] = dae_match.group(1)
        else:
            dae_match2 = re.search(r"(\d+/\d{4})\s*Tipo:", texto_completo)
            if dae_match2:
                resultado["dae"] = dae_match2.group(1)

    except Exception as exc:
        log.warning(f"    Error en detalle {url}: {exc}")
    return resultado


# ─────────────────────────────── Main ─────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("Scraper iniciado")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })

    # 1. Obtener senadores: bloques + provincias
    senador_info = scraper_senadores_web(session)
    if not senador_info:
        log.warning("No se pudieron cargar senadores desde la web.")

    # 2. Cargar proyectos históricos (trazabilidad.tsv)
    historicos = cargar_historicos(ARCHIVO_HISTORICOS, senador_info)

    # 3. Definir rango de fechas para scraping
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

    # 4. Buscar expedientes frescos
    try:
        expedientes = buscar_por_fechas(session, fecha_desde, fecha_hasta)
    except Exception as exc:
        log.error(f"Error en la búsqueda principal: {exc}")
        expedientes = []

    # 5. Enriquecer cada expediente fresco con datos del detalle
    frescos = []
    total = len(expedientes)

    for i, exp in enumerate(expedientes, 1):
        log.info(f"  [{i:>3}/{total}] {exp['tipo']} {exp['nro']}/{exp['anio']}")
        time.sleep(PAUSA_ENTRE_REQUESTS)
        detalle = obtener_detalle(session, exp["url"]) if exp["url"] else {}

        autores_raw   = detalle.get("autores_raw", [])
        autores_norm  = [normalizar_autor(a) for a in autores_raw if a.strip()]

        caratula = exp.get("caratula", exp["extracto"])
        autores, coautores = clasificar_autores(caratula, autores_norm)

        bloques    = get_bloques(autores, senador_info)
        provincias = get_provincias(autores, senador_info)

        frescos.append({
            "nro":        exp["nro"],
            "anio":       exp["anio"],
            "tipo":       exp["tipo"],
            "tipo_label": TIPOS.get(exp["tipo"], exp["tipo"]),
            "extracto":   exp["extracto"],
            "autores":    autores,
            "coautores":  coautores,
            "bloques":    bloques,
            "provincias": provincias,
            "comisiones": detalle.get("comisiones", []),
            "fecha":      exp["fecha"],
            "dae":        detalle.get("dae", ""),
            "origen":     exp["origen"],
            "url":        exp["url"],
        })

    log.info(f"  → {len(frescos)} proyectos frescos")

    # 6. Combinar: frescos + históricos (sin duplicados)
    vistos = set()
    proyectos = []

    for p in frescos:
        key = (p["nro"], p["anio"], p["tipo"])
        if key not in vistos:
            vistos.add(key)
            proyectos.append(p)

    for p in historicos:
        key = (p["nro"], p["anio"], p["tipo"])
        if key not in vistos:
            vistos.add(key)
            proyectos.append(p)

    log.info(f"  → {len(proyectos)} proyectos combinados ({len(frescos)} frescos + {len(historicos)} históricos, {len(frescos)+len(historicos)-len(proyectos)} duplicados)")

    con_bloque = sum(1 for p in proyectos if p["bloques"] and p["bloques"] != ["Sin datos"])
    log.info(f"  → {con_bloque}/{len(proyectos)} con bloque político identificado")

    if not proyectos:
        log.warning("No hay proyectos. Saliendo sin generar HTML.")
        sys.exit(0)

    # 7. Generar dashboard HTML
    titulo = f"Actualizado {hoy.strftime('%d/%m/%Y')}"
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
