import csv
import json
import os
import unicodedata
from datetime import datetime, timedelta

ARCHIVO = os.getenv("ARCHIVO_HISTORICOS", "trazabilidad.tsv")
CSV_SENADORES = os.getenv("CSV_SENADORES", "senadores_vigentes.csv")

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaración",
    "PC": "Proyecto de Comunicación",
    "PR": "Proyecto de Resolución",
    "CA": "Com. de Auditoría",
    "AC": "Acuerdo",
    "CV": "Com. Varias",
}


def normalizar(s):
    s = str(s).upper().strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def cargar_senadores():
    """Lee senadores_vigentes.csv y devuelve dos dicts para lookup de dos niveles:
    - por_apellido:       {apellido_norm: {bloque, provincia}}
    - por_apellido_nombre: {apellido_norm + '_' + primer_nombre_norm: {bloque, provincia}}
    El segundo nivel desambigua cuando dos senadores comparten apellido (ej: LOPEZ).
    """
    por_apellido = {}
    por_apellido_nombre = {}
    try:
        with open(CSV_SENADORES, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                apellido = row.get("APELLIDO", "").strip()
                nombre = row.get("NOMBRE", "").strip()
                clave_ap = normalizar(apellido)
                if not clave_ap:
                    continue
                datos = {
                    "bloque": row.get("BLOQUE", "").strip(),
                    "provincia": row.get("PROVINCIA", "").strip(),
                }
                primer_nombre = normalizar(nombre.split()[0]) if nombre else ""
                clave_ap_nom = f"{clave_ap}_{primer_nombre}" if primer_nombre else clave_ap
                por_apellido[clave_ap] = datos
                por_apellido_nombre[clave_ap_nom] = datos
    except FileNotFoundError:
        print(f"Advertencia: no se encontró {CSV_SENADORES}, bloque/provincia quedarán vacíos.")
    return por_apellido, por_apellido_nombre


def parse_fecha_mesa(valor):
    """Extrae DD/MM/YYYY del campo MESA que tiene formato 'DD/MM/YYYY -'."""
    parte = valor.strip().split(" ")[0]
    try:
        return datetime.strptime(parte, "%d/%m/%Y")
    except ValueError:
        return None


def buscar_senador(autor, por_apellido, por_apellido_nombre):
    """Busca datos del primer firmante. Intenta apellido+primer_nombre antes que solo apellido."""
    partes = autor.split(",", 1)
    apellido_norm = normalizar(partes[0].strip())
    if len(partes) > 1:
        nombre_completo = partes[1].split(" -")[0].strip()
        primer_nombre_norm = normalizar(nombre_completo.split()[0]) if nombre_completo else ""
        clave_full = f"{apellido_norm}_{primer_nombre_norm}"
        if clave_full in por_apellido_nombre:
            return por_apellido_nombre[clave_full]
    return por_apellido.get(apellido_norm, {})


def main():
    por_apellido, por_apellido_nombre = cargar_senadores()
    print(f"Senadores cargados: {len(por_apellido_nombre)} (únicos por apellido+nombre)")

    ahora = datetime.now()
    hace_24h = ahora - timedelta(hours=24)

    proyectos = []
    total_leidas = 0

    with open(ARCHIVO, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for fila in reader:
            total_leidas += 1
            fecha = parse_fecha_mesa(fila.get("MESA", ""))
            if fecha is None:
                continue
            if not (hace_24h <= fecha <= ahora):
                continue

            nro = fila.get("NRO", "").strip()
            anio = fila.get("ANIO", "").strip()
            origen = fila.get("ORIGEN", "").strip()
            tipo = fila.get("TIPO", "").strip()
            caratula = fila.get("CARATULA", "").strip()
            autor = fila.get("AUTOR", "").strip()

            titulo = caratula.split(":", 1)[1].strip() if ":" in caratula else caratula

            datos_senador = buscar_senador(autor, por_apellido, por_apellido_nombre)

            comisiones = [
                fila.get(c, "").strip()
                for c in ("COM1", "COM2", "COM3", "COM4", "COM5")
                if fila.get(c, "").strip()
            ]

            anio_corto = str(anio)[-2:] if len(str(anio)) >= 2 else anio
            url = (
                f"https://www.senado.gob.ar/parlamentario/comisiones/verExp/"
                f"{nro}.{anio_corto}/{origen}/{tipo}"
            )

            proyectos.append({
                "expediente": f"{nro}/{anio}",
                "tipo": tipo,
                "tipo_label": TIPOS.get(tipo, tipo),
                "titulo": titulo,
                "autor": autor,
                "bloque": datos_senador.get("bloque", ""),
                "provincia": datos_senador.get("provincia", ""),
                "fecha": fecha.strftime("%d/%m/%Y"),
                "comisiones": " | ".join(comisiones),
                "url": url,
            })

    resultado = {
        "fecha_generacion": ahora.strftime("%d/%m/%Y %H:%M"),
        "total": len(proyectos),
        "proyectos": proyectos,
    }

    with open("resumen_diario.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"Filas leídas: {total_leidas} | Filas en últimas 24hs: {len(proyectos)}")


if __name__ == "__main__":
    main()
