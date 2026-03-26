#!/usr/bin/env python3
"""
scraper_senado.py — Scraper automático del Senado de la Nación Argentina
=========================================================================
Obtiene todos los proyectos ingresados por Mesa de Entradas, obtiene los
bloques políticos actuales de los senadores directamente de la web del
Senado, y llama a generar_html.py para publicar el dashboard.

Uso manual:
    python scraper_senado.py

Variables de entorno opcionales:
    FECHA_DESDE      Fecha de inicio fija en formato DD/MM/YYYY (ej: 01/03/2026).
                     Si está definida, ignora VENTANA_DIAS.
    VENTANA_DIAS     Días hacia atrás a buscar (default: 30). Se usa solo si
                     FECHA_DESDE no está definida.
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
ARCHIVO_SALIDA   = os.getenv("ARCHIVO_SALIDA", "index.html")

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
    """
    Convierte distintos formatos al estándar "APELLIDO, NOMBRE":
      "Soria , Martin Ignacio"  → "SORIA, MARTIN IGNACIO"
      "SORIA, MARTIN IGNACIO"   → "SORIA, MARTIN IGNACIO"
      "Abad, Maximiliano"       → "ABAD, MAXIMILIANO"
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


# ─────────────────────────────── Senadores (web) ─────────────────────────────

def scraper_senadores_web(session):
    """
    Obtiene el padrón de senadores con sus bloques actuales desde la web.
    Usa dos páginas:
      1. listaSenadoRes         → nombres en "Apellido, Nombre" + ID
      2. agrupados-por-bloques  → bloque real de cada senador + ID
    Retorna: {"APELLIDO, NOMBRE": "Nombre del Bloque"}
    """
    log.info("Scraping senadores desde la web del Senado...")

    # ── Paso 1: Lista alfabética → {id: "APELLIDO, NOMBRE"} ──────────────
    nombres = {}
    try:
        resp = session.get(URL_SENADORES_ALFA, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for link in soup.select("a[href*='/senadores/senador/']"):
            href = link.get("href", "")
            m = re.search(r"/senadores/senador/(\d+)", href)
            if m:
                sid  = m.group(1)
                name = link.get_text(strip=True)
                if "," in name and sid not in nombres:
                    nombres[sid] = normalizar_autor(name)

        log.info(f"  → {len(nombres)} senadores en lista alfabética")
    except Exception as exc:
        log.error(f"  Error obteniendo lista alfabética: {exc}")
        return {}

    time.sleep(0.5)

    # ── Paso 2: Agrupados por bloque → {id: bloque} ──────────────────────
    bloques_por_id = {}
    try:
        resp = session.get(URL_SENADORES_BLOQUE, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Recorrer filas rastreando el bloque actual
        # (las celdas con rowspan hacen que algunas filas no tengan la
        #  primera celda, así que mantenemos current_bloque entre filas)
        current_bloque = None

        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if not tds:
                continue

            # Revisar si la primera celda es un nombre de bloque
            # (no contiene links a senadores)
            primera = tds[0]
            links_en_primera = primera.select("a[href*='/senadores/senador/']")
            if not links_en_primera:
                texto = primera.get_text(strip=True)
                # Ignorar encabezados de tabla
                if texto and texto.lower() not in ("bloque", "presidente/a",
                    "integrantes", "contacto", ""):
                    current_bloque = texto

            # Encontrar TODOS los links a senadores en toda la fila
            for link in tr.select("a[href*='/senadores/senador/']"):
                href = link.get("href", "")
                m = re.search(r"/senadores/senador/(\d+)", href)
                if m and current_bloque:
                    bloques_por_id[m.group(1)] = current_bloque

        log.info(f"  → {len(bloques_por_id)} senadores en página de bloques")
    except Exception as exc:
        log.error(f"  Error obteniendo bloques: {exc}")
        return {}

    # ── Paso 3: Combinar ─────────────────────────────────────────────────
    padron = {}
    for sid, nombre_norm in nombres.items():
        padron[nombre_norm] = bloques_por_id.get(sid, "Sin datos")

    con_bloque = sum(1 for v in padron.values() if v != "Sin datos")
    log.info(f"  → {len(padron)} senadores totales, {con_bloque} con bloque asignado")
    return padron


# ─────────────────────────────── Scraping: búsqueda ──────────────────────────

def obtener_token(session):
    """Obtiene un CSRF token fresco de la página principal de búsqueda."""
    log.info("Obteniendo CSRF token...")
    resp = session.get(URL_BUSQUEDA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    inp = soup.find("input", {"name": "busqueda_proyectos[_token]"})
    if not inp:
        raise RuntimeError("No se encontró el campo busqueda_proyectos[_token]")
    return inp["value"]


def parsear_tabla_resultados(html):
    """Extrae filas de la tabla de resultados de búsqueda."""
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
    """POST inicial + paginación GET."""
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
    """
    Visita la página de detalle de un expediente y extrae:
        autores_raw  : lista de nombres (desde el atributo title de los links)
        comisiones   : lista de nombres de comisiones
        dae          : número de DAE (ej: "8/2026")
    """
    resultado = {"autores_raw": [], "comisiones": [], "dae": ""}
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ── AUTORES ──────────────────────────────────────────────
        # Los autores son links <a href="/senadores/senador/ID">
        # El atributo "title" tiene el nombre en formato "APELLIDO, NOMBRE"
        for link in soup.select("a[href*='/senadores/senador/']"):
            title = link.get("title", "").strip()
            texto = link.get_text(strip=True)
            nombre = title if title else texto
            if nombre:
                resultado["autores_raw"].append(nombre)

        # ── COMISIONES ───────────────────────────────────────────
        # Buscar filas de tabla que contengan "ORDEN DE GIRO"
        for tr in soup.select("table tr"):
            texto_fila = tr.get_text(" ", strip=True)
            if "ORDEN DE GIRO" in texto_fila:
                primera_celda = tr.find("td")
                if primera_celda:
                    com_text = primera_celda.get_text(strip=True)
                    com = re.sub(r"\s*ORDEN DE GIRO:\s*\d+.*$", "", com_text).strip()
                    if com:
                        resultado["comisiones"].append(com)

        # ── DAE ──────────────────────────────────────────────────
        # Buscar "D.A.E." en el texto de la página y extraer el número
        texto_completo = soup.get_text()
        dae_match = re.search(r"D\.A\.E\.\s*(\d+/\d{4})", texto_completo)
        if dae_match:
            resultado["dae"] = dae_match.group(1)
        else:
            # Fallback: buscar patrón "N°/YYYY Tipo:"
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

    # 1. Crear sesión HTTP
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })

    # 2. Obtener senadores y bloques desde la web
    senador_bloque = scraper_senadores_web(session)
    if not senador_bloque:
        log.warning("No se pudieron cargar senadores desde la web.")

    # 3. Definir rango de fechas
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

    # 4. Buscar expedientes
    try:
        expedientes = buscar_por_fechas(session, fecha_desde, fecha_hasta)
    except Exception as exc:
        log.error(f"Error en la búsqueda principal: {exc}")
        sys.exit(1)

    if not expedientes:
        log.warning("No se encontraron expedientes. Saliendo sin generar HTML.")
        sys.exit(0)

    # 5. Enriquecer cada expediente con datos del detalle
    proyectos = []
    total = len(expedientes)

    for i, exp in enumerate(expedientes, 1):
        log.info(f"  [{i:>3}/{total}] {exp['tipo']} {exp['nro']}/{exp['anio']}")

        time.sleep(PAUSA_ENTRE_REQUESTS)
        detalle = obtener_detalle(session, exp["url"]) if exp["url"] else {}

        # Los autores vienen del atributo "title" de los links, ya en
        # formato "APELLIDO, NOMBRE" o similar. Normalizamos por seguridad.
        autores_raw   = detalle.get("autores_raw", [])
        autores_norm  = [normalizar_autor(a) for a in autores_raw if a.strip()]
        bloques       = get_bloques(autores_norm, senador_bloque)

        proyectos.append({
            "nro":        exp["nro"],
            "anio":       exp["anio"],
            "tipo":       exp["tipo"],
            "tipo_label": TIPOS.get(exp["tipo"], exp["tipo"]),
            "extracto":   exp["extracto"],
            "autores":    autores_norm,
            "bloques":    bloques,
            "comisiones": detalle.get("comisiones", []),
            "fecha":      exp["fecha"],
            "dae":        detalle.get("dae", ""),
            "origen":     exp["origen"],
            "url":        exp["url"],
        })

    log.info(f"  → {len(proyectos)} proyectos procesados")

    # Conteo rápido de bloques para verificar matching
    con_bloque = sum(1 for p in proyectos if p["bloques"] and p["bloques"] != ["Sin datos"])
    log.info(f"  → {con_bloque}/{len(proyectos)} con bloque político identificado")

    # 6. Generar dashboard HTML
    if FECHA_DESDE_FIJA:
        titulo = f"Desde {FECHA_DESDE_FIJA} · Actualizado {hoy.strftime('%d/%m/%Y')}"
    else:
        titulo = f"Últimos {VENTANA_DIAS} días · Actualizado {hoy.strftime('%d/%m/%Y')}"
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
