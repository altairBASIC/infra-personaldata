"""
generar_datos.py — Generador de correos sintéticos .mbox

Genera un archivo .mbox con correos sintéticos para probar la tubería:
  - Correos BUENOS: cumplen las 6 reglas de calidad, deben llegar a Silver.
  - Correos MALOS: rompen una regla cada uno, deben ser descartados.

Es ALEATORIO pero REPRODUCIBLE: usa una semilla fija, así que cada corrida
con la misma semilla produce exactamente los mismos correos.

Reglas que el generador puede romper desde la entrada:
  r01 → actor con email inválido
  r02 → timestamp en el futuro
  r03 → content_text demasiado corto
  r04 → raw_id (Message-ID) duplicado

Reglas que NO se pueden romper desde el generador (documentado):
  r05 → encoding inválido (el parser lo repara antes de validar)
  r06 → signal_id (lo calcula la tubería, no viene en el correo)

Uso:
    python generar_datos.py                  # valores por defecto
    python generar_datos.py --semilla 7      # otra semilla
    python generar_datos.py --salida x.mbox  # otro archivo de salida
"""

from __future__ import annotations

import argparse
import mailbox
import random
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone


REMITENTES = [
    ("Ana Pérez", "ana@ejemplo.com"),
    ("John Smith", "john@example.com"),
    ("María González", "maria@ejemplo.com"),
    ("DevOps Team", "devops@example.com"),
    ("Carlos Ruiz", "carlos@ejemplo.com"),
    ("Sarah Connor", "sarah@example.com"),
    ("Lucía Fernández", "lucia@ejemplo.com"),
    ("Mike Johnson", "mike@example.com"),
]

PLANTILLAS = [
    ("Reunión del proyecto", "Hola equipo, confirmo la reunión del viernes a las 10. Saludos."),
    ("Project update", "Hi team, here is the weekly update on the migration. Everything is on track."),
    ("Factura de marzo", "Estimado cliente, adjunto la factura del mes. Quedo atenta a consultas."),
    ("Scheduled maintenance", "Notice: the production database will undergo maintenance this Saturday."),
    ("Invitación a charla", "Hola, te invito a la charla sobre infraestructura de datos del jueves."),
    ("Vacation request", "Hello, I would like to request vacation days for the last week of July."),
    ("Resumen semanal", "Buenas, les comparto el resumen de las métricas del equipo esta semana."),
    ("Security alert", "Warning: a critical security update is available for the main server."),
]

CANALES = ["Trabajo", "Work", "Finanzas", "Alerts", "Eventos", "HR", "Personal"]


def crear_correo(message_id, remitente, asunto, cuerpo, canal, fecha):
    """Construye un EmailMessage bien formado a partir de sus piezas."""
    nombre, email = remitente
    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["From"] = f"{nombre} <{email}>"
    msg["Date"] = format_datetime(fecha)
    msg["Subject"] = asunto
    msg["X-Gmail-Labels"] = canal
    msg.set_content(cuerpo)
    return msg


def generar_buenos(rng, cantidad):
    """Genera correos buenos combinando piezas al azar."""
    correos = []
    for i in range(cantidad):
        remitente = rng.choice(REMITENTES)
        asunto, cuerpo = rng.choice(PLANTILLAS)
        canal = rng.choice(CANALES)
        fecha = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
            days=rng.randint(1, 90),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        message_id = f"<bueno-{i:03d}@ejemplo.com>"
        correos.append(crear_correo(message_id, remitente, asunto, cuerpo, canal, fecha))
    return correos


def generar_malos(rng, cantidad):
    """Genera correos malos. Cada uno rompe una de las 4 reglas rompibles."""
    correos = []
    reglas_rompibles = ["r01", "r02", "r03", "r04"]
    for i in range(cantidad):
        regla = rng.choice(reglas_rompibles)
        remitente = rng.choice(REMITENTES)
        asunto, cuerpo = rng.choice(PLANTILLAS)
        canal = rng.choice(CANALES)
        fecha = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
        message_id = f"<malo-{i:03d}@ejemplo.com>"

        if regla == "r01":
            msg = crear_correo(message_id, ("Sin Email", "noesunemail"), asunto, cuerpo, canal, fecha)
        elif regla == "r02":
            fecha_futura = datetime(2050, 1, 1, 12, 0, tzinfo=timezone.utc)
            msg = crear_correo(message_id, remitente, asunto, cuerpo, canal, fecha_futura)
        elif regla == "r03":
            msg = crear_correo(message_id, remitente, asunto, "ok", canal, fecha)
        elif regla == "r04":
            msg = crear_correo("<bueno-000@ejemplo.com>", remitente, asunto, cuerpo, canal, fecha)

        correos.append((regla, msg))
    return correos


def generar_correos(semilla=42):
    """Genera la lista completa de correos (buenos + malos), mezclados.

    Esta función NO escribe archivos: solo devuelve los datos. Eso la hace
    fácil de testear (un test puede examinar los correos sin tocar disco).

    Devuelve una tupla (correos, info) donde:
      - correos: lista de EmailMessage, ya mezclados
      - info: dict con n_buenos, n_malos y conteo de reglas rotas
    """
    rng = random.Random(semilla)
    n_buenos = rng.randint(5, 10)
    n_malos = rng.randint(4, 8)

    buenos = generar_buenos(rng, n_buenos)
    malos = generar_malos(rng, n_malos)

    todos = [("bueno", c) for c in buenos] + [(regla, c) for regla, c in malos]
    rng.shuffle(todos)

    conteo_reglas = {}
    correos = []
    for tipo, correo in todos:
        correos.append(correo)
        if tipo != "bueno":
            conteo_reglas[tipo] = conteo_reglas.get(tipo, 0) + 1

    info = {
        "n_buenos": n_buenos,
        "n_malos": n_malos,
        "reglas_rotas": dict(sorted(conteo_reglas.items())),
    }
    return correos, info


def escribir_mbox(correos, ruta):
    """Escribe una lista de correos en un archivo .mbox."""
    buzon = mailbox.mbox(ruta)
    buzon.clear()  # idempotente
    for correo in correos:
        buzon.add(correo)
    buzon.flush()
    buzon.close()


def main():
    parser = argparse.ArgumentParser(description="Genera correos sintéticos .mbox")
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--salida", type=str, default="correos_prueba.mbox")
    args = parser.parse_args()

    correos, info = generar_correos(semilla=args.semilla)
    escribir_mbox(correos, args.salida)

    print(f"Listo: {len(correos)} correos escritos en '{args.salida}' (semilla={args.semilla})")
    print(f"  - {info['n_buenos']} buenos (deberían pasar las reglas)")
    print(f"  - {info['n_malos']} malos (deberían ser descartados)")
    print(f"  - reglas rotas: {info['reglas_rotas']}")


if __name__ == "__main__":
    main()