#!/usr/bin/env python3
"""
generar_html_resumen.py — Genera resumen_diario.html a partir de resumen_diario.json.
Exporta generar_html(data) para que enviar_email.py pueda reutilizarla.
"""
import json
import os
from collections import Counter, defaultdict
from datetime import datetime

RESUMEN_JSON = os.getenv("RESUMEN_JSON", "resumen_diario.json")
RESUMEN_HTML = os.getenv("RESUMEN_HTML", "resumen_diario.html")

TIPOS = {
    "PL": "Proyectos de Ley",
    "PD": "Proyectos de Declaración",
    "PC": "Proyectos de Comunicación",
    "PR": "Proyectos de Resolución",
    "CA": "Com. de Auditoría",
    "AC": "Acuerdo",
    "CV": "Com. Varias",
}
TIPOS_CORTO = {
    "PL": "Proy. de Ley",
    "PR": "Proy. de Resolución",
    "PD": "Proy. de Declaración",
    "PC": "Proy. de Comunicación",
    "CA": "Com. de Auditoría",
    "AC": "Acuerdo",
    "CV": "Com. Varias",
}
ORDEN_TIPOS = ["PL", "PR", "PD", "PC", "CA", "AC", "CV"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
DASHBOARD_URL = "https://bonifaciomariano.github.io/Proyectos-ingresados"


def _fecha_larga(fecha_str):
    try:
        dt = datetime.strptime(fecha_str, "%d/%m/%Y")
        return f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}"
    except ValueError:
        return fecha_str


def _metricas_cells(proyectos):
    """Devuelve lista de (label, n, color) para las 3 celdas de tipo."""
    conteo = Counter(p["tipo"] for p in proyectos)
    ordenados = sorted(conteo.items(), key=lambda x: -x[1])
    top = ordenados[:3]
    otros = sum(v for _, v in ordenados[3:]) if len(ordenados) > 3 else 0

    cells = []
    for tipo, n in top:
        color = "#1a5fa5" if tipo == "PL" else "#1a1a1a"
        cells.append((TIPOS_CORTO.get(tipo, tipo), n, color))

    if otros:
        cells = cells[:2] + [("Otros", otros, "#1a1a1a")]

    while len(cells) < 3:
        cells.append(("", "", "#1a1a1a"))

    return cells


def _celda_tipo(label, valor, color):
    if not label:
        return '<td width="23%" style="font-size:0;">&nbsp;</td>'
    return (
        f'<td width="23%" style="background-color:#F5F5F5; border:1px solid #E5E5E5;'
        f' padding:14px 8px; text-align:center;">'
        f'<p style="margin:0 0 4px 0; font-size:11px; color:#999999; text-transform:uppercase;'
        f' letter-spacing:0.5px; font-family:Tahoma,Geneva,sans-serif;">{label}</p>'
        f'<p style="margin:0; font-size:22px; font-weight:700; color:{color};'
        f' font-family:Tahoma,Geneva,sans-serif;">{valor}</p>'
        f'</td>'
    )


def _bloques_html(proyectos):
    conteo = defaultdict(int)
    for p in proyectos:
        bloque = (p.get("bloque") or "Sin datos").strip() or "Sin datos"
        conteo[bloque] += 1
    total = len(proyectos)
    filas = []
    for bloque, n in sorted(conteo.items(), key=lambda x: -x[1]):
        pct = round((n / total) * 100) if total else 0
        rest = 100 - pct
        filas.append(
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">'
            f'<tr><td style="font-size:12px; color:#1a1a1a; padding-bottom:3px;'
            f' font-family:Tahoma,Geneva,sans-serif;" colspan="2">'
            f'{bloque} <span style="color:#999999;">({n})</span></td></tr>'
            f'<tr>'
            f'<td width="{pct}%" style="height:6px; background-color:#1a5fa5; font-size:0;">&nbsp;</td>'
            f'<td width="{rest}%" style="height:6px; background-color:#E5E5E5; font-size:0;">&nbsp;</td>'
            f'</tr></table>'
        )
    return "\n".join(filas) if filas else '<p style="font-size:12px; color:#999999;">Sin datos de bloque.</p>'


def _comisiones_html(proyectos):
    conteo = defaultdict(int)
    for p in proyectos:
        for c in (p.get("comisiones") or "").split(" | "):
            c = c.strip()
            if c:
                conteo[c] += 1
    if not conteo:
        return '<p style="font-size:12px; color:#999999; font-family:Tahoma,Geneva,sans-serif;">Sin comisiones asignadas.</p>'
    filas = []
    for com, n in sorted(conteo.items(), key=lambda x: -x[1]):
        filas.append(
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:6px;">'
            f'<tr>'
            f'<td style="font-size:12px; color:#1a1a1a; font-family:Tahoma,Geneva,sans-serif;">{com}</td>'
            f'<td align="right"><span style="display:inline-block; background-color:#EEEEEE;'
            f' color:#666666; font-size:11px; padding:1px 7px;'
            f' font-family:Tahoma,Geneva,sans-serif;">{n}</span></td>'
            f'</tr></table>'
        )
    return "\n".join(filas)


def _proyectos_html(proyectos):
    grupos = defaultdict(list)
    for p in proyectos:
        grupos[p["tipo"]].append(p)

    secciones = []
    for tipo in ORDEN_TIPOS:
        if tipo not in grupos:
            continue
        lista = grupos[tipo]
        label = TIPOS.get(tipo, tipo)

        secciones.append(
            f'<tr><td style="padding:0 28px 0 28px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="background-color:#F5F5F5; border-left:3px solid #1a5fa5; padding:8px 12px;">'
            f'<p style="margin:0; font-size:13px; font-weight:700; color:#1a5fa5;'
            f' font-family:Tahoma,Geneva,sans-serif;">'
            f'{label} <span style="font-weight:400; color:#666666;">({len(lista)})</span>'
            f'</p></td></tr></table></td></tr>'
        )

        for p in lista:
            expediente = p.get("expediente", "")
            titulo = p.get("titulo", "")
            autor = p.get("autor", "")
            bloque = (p.get("bloque") or "").strip()
            provincia = (p.get("provincia") or "").strip()
            comisiones = (p.get("comisiones") or "").strip()
            url = p.get("url", "#")

            linea2_partes = [f'<span style="color:#666666;">{autor}</span>']
            if bloque:
                linea2_partes.append(f'<span style="color:#999999;">{bloque}</span>')
            if provincia:
                linea2_partes.append(f'<span style="color:#999999;">{provincia}</span>')
            linea2 = " &nbsp;·&nbsp; ".join(linea2_partes)

            linea3 = (
                f'<p style="margin:0; font-size:12px; color:#999999; line-height:1.4;'
                f' font-family:Tahoma,Geneva,sans-serif;">{comisiones}</p>'
                if comisiones else ""
            )

            secciones.append(
                f'<tr><td style="padding:0 28px;">'
                f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
                f'<td style="padding:12px 0 11px 0; border-bottom:1px solid #E5E5E5;">'
                f'<p style="margin:0 0 4px 0; font-size:13px; color:#1a1a1a; line-height:1.4;'
                f' font-family:Tahoma,Geneva,sans-serif;">'
                f'<a href="{url}" style="color:#1a5fa5; text-decoration:underline; font-weight:700;'
                f' font-family:Tahoma,Geneva,sans-serif;">{expediente}</a>'
                f' &nbsp;—&nbsp;{titulo}</p>'
                f'<p style="margin:0 0 3px 0; font-size:12px; line-height:1.4;'
                f' font-family:Tahoma,Geneva,sans-serif;">{linea2}</p>'
                f'{linea3}'
                f'</td></tr></table></td></tr>'
            )

        secciones.append('<tr><td style="height:12px;"></td></tr>')

    return "\n".join(secciones)


def generar_html(data):
    """Genera y retorna el HTML completo del resumen diario."""
    proyectos = data.get("proyectos", [])
    total = data.get("total", 0)
    fecha_str = data.get("proyectos_fecha", "")
    generado = data.get("generado", "")
    hora = generado.split(" ")[1] if " " in generado else ""
    fecha_lg = _fecha_larga(fecha_str)

    cells = _metricas_cells(proyectos)
    celda_total = (
        f'<td width="25%" style="background-color:#F5F5F5; border:1px solid #E5E5E5;'
        f' padding:14px 8px; text-align:center;">'
        f'<p style="margin:0 0 4px 0; font-size:11px; color:#999999; text-transform:uppercase;'
        f' letter-spacing:0.5px; font-family:Tahoma,Geneva,sans-serif;">Total</p>'
        f'<p style="margin:0; font-size:22px; font-weight:700; color:#1a1a1a;'
        f' font-family:Tahoma,Geneva,sans-serif;">{total}</p>'
        f'</td>'
    )
    celdas_tipo = "\n".join(
        f'<td width="2%" style="font-size:0;">&nbsp;</td>\n{_celda_tipo(l, n, c)}'
        for l, n, c in cells
    )

    if total == 0:
        cuerpo = (
            '<tr><td style="padding:20px 28px; text-align:center; color:#999999;'
            ' font-family:Tahoma,Geneva,sans-serif; font-size:14px;">'
            'No hubo proyectos ingresados este día.</td></tr>'
        )
    else:
        cuerpo = (
            '<tr><td style="padding:0 28px 8px 28px;">'
            '<p style="margin:0 0 12px 0; font-size:13px; font-weight:700; color:#1a1a1a;'
            ' text-transform:uppercase; letter-spacing:0.5px; font-family:Tahoma,Geneva,sans-serif;">'
            'Detalle de proyectos</p></td></tr>\n'
            + _proyectos_html(proyectos)
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Proyectos ingresados — {fecha_lg}</title>
</head>
<body style="margin:0; padding:0; background-color:#F0F0F0; font-family:Tahoma,Geneva,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F0F0F0;">
  <tr>
    <td align="center" style="padding:20px 10px;">

      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px; width:100%; background-color:#FFFFFF; font-family:Tahoma,Geneva,sans-serif;">

        <!-- A. ENCABEZADO -->
        <tr>
          <td style="background-color:#1a5fa5; padding:24px 28px 20px 28px;">
            <p style="margin:0 0 4px 0; font-size:11px; color:#FFFFFF; letter-spacing:1.5px;
               text-transform:uppercase; font-family:Tahoma,Geneva,sans-serif;">
              Senado de la Nación Argentina
            </p>
            <h1 style="margin:0 0 6px 0; font-size:22px; color:#FFFFFF; font-weight:700;
                line-height:1.2; font-family:Tahoma,Geneva,sans-serif;">
              Proyectos ingresados — {fecha_lg}
            </h1>
            <p style="margin:0; font-size:13px; color:#FFFFFF; font-family:Tahoma,Geneva,sans-serif;">
              Generado a las {hora} ART
            </p>
          </td>
        </tr>
        <tr><td style="height:3px; background-color:#E5E5E5;"></td></tr>

        <!-- B. MÉTRICAS -->
        <tr>
          <td style="padding:20px 28px 16px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                {celda_total}
                {celdas_tipo}
              </tr>
            </table>
          </td>
        </tr>

        <!-- C. PANELES DE RESUMEN -->
        <tr>
          <td style="padding:0 28px 20px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr valign="top">
                <td width="48%" style="background-color:#F5F5F5; border:1px solid #E5E5E5; padding:14px 16px;">
                  <p style="margin:0 0 12px 0; font-size:12px; font-weight:700; color:#1a1a1a;
                     text-transform:uppercase; letter-spacing:0.5px; font-family:Tahoma,Geneva,sans-serif;">
                    Por bloque
                  </p>
                  {_bloques_html(proyectos)}
                </td>
                <td width="4%" style="font-size:0;">&nbsp;</td>
                <td width="48%" style="background-color:#F5F5F5; border:1px solid #E5E5E5; padding:14px 16px;">
                  <p style="margin:0 0 12px 0; font-size:12px; font-weight:700; color:#1a1a1a;
                     text-transform:uppercase; letter-spacing:0.5px; font-family:Tahoma,Geneva,sans-serif;">
                    Por comisión
                  </p>
                  {_comisiones_html(proyectos)}
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- D. DETALLE -->
        {cuerpo}

        <!-- E. PIE -->
        <tr><td style="height:1px; background-color:#E5E5E5;"></td></tr>
        <tr>
          <td style="padding:16px 28px; background-color:#F5F5F5;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr valign="middle">
                <td style="font-size:11px; color:#999999; font-family:Tahoma,Geneva,sans-serif;">
                  Fuente: scraper automático HSN &nbsp;·&nbsp; {generado}
                </td>
                <td align="right" style="font-size:11px;">
                  <a href="{DASHBOARD_URL}"
                     style="color:#1a5fa5; text-decoration:underline; font-family:Tahoma,Geneva,sans-serif;">
                    Ver dashboard completo &rarr;
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


def main():
    with open(RESUMEN_JSON, encoding="utf-8") as f:
        data = json.load(f)

    html = generar_html(data)

    with open(RESUMEN_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML generado: {RESUMEN_HTML} ({len(html):,} bytes) — {data['total']} proyectos")


if __name__ == "__main__":
    main()
