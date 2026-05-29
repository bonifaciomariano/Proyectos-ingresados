import csv
import json
import os
from datetime import datetime, timedelta

ARCHIVO = os.getenv("ARCHIVO_HISTORICOS", "trazabilidad.tsv")

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaración",
    "PC": "Proyecto de Comunicación",
    "PR": "Proyecto de Resolución",
    "CA": "Com. de Auditoría",
    "AC": "Acuerdo",
    "CV": "Com. Varias",
}


def parse_fecha_mesa(valor):
    """Extrae DD/MM/YYYY del campo MESA que tiene formato 'DD/MM/YYYY -'."""
    parte = valor.strip().split(" ")[0]
    try:
        return datetime.strptime(parte, "%d/%m/%Y")
    except ValueError:
        return None


def main():
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

            titulo = caratula.split(":", 1)[1].strip() if ":" in caratula else caratula

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
                "autor": fila.get("AUTOR", "").strip(),
                "bloque": fila.get("BLOQUE", "").strip() if "BLOQUE" in fila else "",
                "provincia": fila.get("PROVINCIA", "").strip() if "PROVINCIA" in fila else "",
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
