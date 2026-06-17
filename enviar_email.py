#!/usr/bin/env python3
"""
enviar_email.py — Lee resumen_diario.json y envía el resumen por email vía Gmail SMTP.
Si total=0, termina sin enviar.

Variables de entorno requeridas cuando total>0:
    GMAIL_USER          Dirección Gmail remitente
    GMAIL_APP_PASSWORD  Contraseña de aplicación de Google
    EMAIL_DESTINO       Una o más direcciones separadas por coma
"""
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from generar_html_resumen import generar_html

RESUMEN_JSON = os.getenv("RESUMEN_JSON", "resumen_diario.json")


def main():
    with open(RESUMEN_JSON, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("total", 0) == 0:
        print(f"total=0 para {data.get('proyectos_fecha', '?')} — no se envía email.")
        return

    gmail_user = os.environ["GMAIL_USER"]
    gmail_pwd  = os.environ["GMAIL_APP_PASSWORD"]
    destinos   = [d.strip() for d in os.environ["EMAIL_DESTINO"].split(",") if d.strip()]

    fecha    = data.get("proyectos_fecha", "")
    asunto   = f"Proyectos Senado — {fecha}"
    html_body = generar_html(data)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"]    = gmail_user
    msg["To"]      = ", ".join(destinos)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_pwd)
        smtp.sendmail(gmail_user, destinos, msg.as_string())

    print(f"Email enviado a: {', '.join(destinos)} | Proyectos: {data['total']} | Fecha: {fecha}")


if __name__ == "__main__":
    main()
