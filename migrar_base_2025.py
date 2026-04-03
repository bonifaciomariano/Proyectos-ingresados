"""
migrar_base_2025.py
Reemplaza los registros 2025 en trazabilidad.tsv usando
Trazabilidad-Todas-01-04-2026.xlsx como fuente.
Filtra: TIPO en {PL, PR, CA, AC, CV}
"""

import csv
import sys
from pathlib import Path
from collections import Counter

try:
    import openpyxl
except ImportError:
    sys.exit("ERROR: instalar openpyxl → pip install openpyxl")

# ── Configuración ──────────────────────────────────────────────────────────────
XLSX_PATH = Path("Trazabilidad-Todas-01-04-2026.xlsx")
TSV_PATH  = Path("trazabilidad.tsv")
TIPOS_OK  = {"PL", "PR", "CA", "AC", "CV"}
ENCODING  = "utf-8-sig"

# Índices de columna en el xlsx (base 0, fila de encabezados es row 0)
IDX = {
    "ORIGEN":   0,
    "NRO":      1,
    "ANIO":     2,
    "TIPO":     3,
    "CARATULA": 4,
    "DAE":      5,
    "MESA":     8,
    "AUTOR":    13,
    "COM1":     15,
    "COM2":     19,
    "COM3":     23,
    "COM4":     27,
    "COM5":     31,
}
TSV_COLS = ["ORIGEN","NRO","ANIO","TIPO","CARATULA","DAE","MESA","AUTOR",
            "COM1","COM2","COM3","COM4","COM5"]

def clean(val):
    """Devuelve string limpio o vacío."""
    if val is None:
        return ""
    s = str(val).strip()
    # Quitar trailing ' -' que viene en algunos campos de fecha/DAE
    return s

def int_or_str(val):
    """Convierte números flotantes a entero string."""
    if isinstance(val, float):
        return str(int(val))
    return clean(val)


def leer_xlsx(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    filas = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # saltar encabezados
        tipo = clean(row[IDX["TIPO"]])
        if tipo not in TIPOS_OK:
            continue
        fila = {
            "ORIGEN":   clean(row[IDX["ORIGEN"]]),
            "NRO":      int_or_str(row[IDX["NRO"]]),
            "ANIO":     int_or_str(row[IDX["ANIO"]]),
            "TIPO":     tipo,
            "CARATULA": clean(row[IDX["CARATULA"]]),
            "DAE":      clean(row[IDX["DAE"]]),
            "MESA":     clean(row[IDX["MESA"]]),
            "AUTOR":    clean(row[IDX["AUTOR"]]),
            "COM1":     clean(row[IDX["COM1"]]),
            "COM2":     clean(row[IDX["COM2"]]),
            "COM3":     clean(row[IDX["COM3"]]),
            "COM4":     clean(row[IDX["COM4"]]),
            "COM5":     clean(row[IDX["COM5"]]),
        }
        filas.append(fila)
    wb.close()
    return filas


def leer_tsv(path):
    with open(path, encoding=ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def escribir_tsv(path, filas):
    with open(path, "w", encoding=ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_COLS, delimiter="\t",
                                lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(filas)


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not XLSX_PATH.exists():
        sys.exit(f"ERROR: no se encuentra {XLSX_PATH}")
    if not TSV_PATH.exists():
        sys.exit(f"ERROR: no se encuentra {TSV_PATH}")

    print(f"Leyendo {XLSX_PATH} …")
    nuevas = leer_xlsx(XLSX_PATH)

    conteo = Counter(f["TIPO"] for f in nuevas)
    print("\n── Filas nuevas por TIPO ──────────────")
    for tipo in sorted(conteo):
        print(f"  {tipo}: {conteo[tipo]}")
    print(f"  TOTAL: {len(nuevas)}")

    print(f"\nLeyendo {TSV_PATH} …")
    existentes = leer_tsv(TSV_PATH)
    antes = len(existentes)
    # Conservar filas de años distintos a 2025
    otras = [r for r in existentes if r.get("ANIO", "") != "2025"]
    print(f"  Filas actuales: {antes} | Filas 2025 a reemplazar: {antes - len(otras)}")

    resultado = otras + nuevas
    print(f"  Filas en resultado final: {len(resultado)}")

    print(f"\nEscribiendo {TSV_PATH} …")
    escribir_tsv(TSV_PATH, resultado)
    print("Listo.")
