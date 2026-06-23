"""Genera un mbox sintético robusto con edge cases para pruebas rigurosas."""

import email.message
import email.utils
import mailbox
from datetime import datetime, timedelta, timezone
from pathlib import Path


def msg(from_addr, subject, body, date, msg_id,
        content_type="text/plain", charset="utf-8", channel=None):
    m = email.message.Message()
    m["From"] = from_addr
    m["To"] = "dest@example.com"
    m["Subject"] = subject
    m["Message-ID"] = msg_id
    m["Date"] = email.utils.format_datetime(date)
    m["Content-Type"] = f"{content_type}; charset={charset}"
    if channel:
        m["X-Gmail-Labels"] = channel
    m.set_payload(body, charset=charset)
    return m


def generar():
    ruta = Path("data/input/correos_test.mbox")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    mbox = mailbox.mbox(str(ruta))
    mbox.clear()

    actores = [
        "ana.garcia@empresa.cl", "carlos.lopez@utem.cl",
        "maria.santos@gmail.com", "pedro.ruiz@outlook.com",
        "juanita.flores@empresa.cl", "admin@server.company.org",
        "newsletter@noticias.tech", "soporte@tienda.online.cl",
        "prof.martinez@academia.edu", "ceo@startup.io",
    ]
    temas = [
        ("Reunión de planificación Q3",
         "Estimado equipo, confirmo la reunión de planificación del tercer trimestre "
         "para el próximo lunes a las 10:00. Necesitamos revisar los KPIs pendientes."),
        ("Factura #2024-0891 adjunta",
         "Adjunto la factura correspondiente al servicio de hosting del mes de junio 2024. "
         "El monto total es de 150.000 CLP. Plazo de pago: 30 días."),
        ("Re: Propuesta de migración a contenedores",
         "Revisé la propuesta de migración a Kubernetes. Creo que podemos empezar con un "
         "piloto en staging antes de mover producción. Ahorro estimado: 30%."),
        ("Invitación: Conferencia DevOps Santiago 2024",
         "Te invitamos a la conferencia anual de DevOps en Santiago. Temas: CI/CD, "
         "observabilidad, infraestructura como código. Fecha: 15 agosto 2024."),
        ("Reporte semanal de métricas",
         "Resumen semanal: uptime 99.97%, latencia p95 = 120ms, 3 incidentes menores "
         "resueltos. El deploy del viernes fue exitoso sin rollback."),
        ("Solicitud de vacaciones",
         "Solicito formalmente mis vacaciones del 22 al 31 de julio de 2024. "
         "Ya coordiné con el equipo la cobertura durante mi ausencia."),
        ("Actualización de seguridad urgente",
         "Se detectó una vulnerabilidad CVE-2024-1234 en OpenSSL. Es necesario actualizar "
         "todos los servidores a la versión 3.2.1 antes del viernes."),
        ("Feedback del sprint review",
         "El sprint review fue positivo. El cliente quedó conforme con las 3 historias "
         "entregadas. Hay 2 bugs menores que se priorizarán en el siguiente sprint."),
        ("Presupuesto infraestructura 2025",
         "Borrador del presupuesto 2025. Rubros: cloud 45%, licencias 25%, equipo 20%, "
         "contingencia 10%. Total estimado: 120 millones CLP."),
        ("Onboarding nuevo integrante",
         "Bienvenido Tomás al equipo de backend. Primer día: lunes. Necesita acceso a "
         "GitLab, Jira, Slack, VPN corporativa y ambiente de staging."),
    ]
    canales = ["Inbox", "Work", "Projects", None, "Newsletters",
               None, "Urgent", "Work", None, "HR"]
    base = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

    # --- GRUPO 1: 10 correos limpios variados ---
    for i, (subj, body) in enumerate(temas):
        dt = base + timedelta(days=i * 12, hours=i * 2, minutes=i * 17)
        mbox.add(msg(actores[i], subj, body, dt,
                     f"<clean-{i:03d}@test.local>", channel=canales[i]))

    # --- GRUPO 2: 20 correos de seguimiento (volumen para Gold) ---
    for i in range(20):
        idx = i % len(actores)
        dt = base + timedelta(days=120 + i * 5, hours=i)
        body = (f"Seguimiento #{i+11}: contenido suficiente para la regla de longitud "
                f"mínima y para probar las agregaciones Gold de forma robusta.")
        mbox.add(msg(actores[idx], f"Seguimiento #{i+11}", body, dt,
                     f"<followup-{i:03d}@test.local>"))

    # --- GRUPO 3: HTML ---
    html1 = ("<html><body><h1>Alerta de monitoreo</h1>"
             "<p>El servidor <b>prod-db-01</b> excedió el 90% de uso de CPU.</p>"
             "<p>Acción requerida: escalar antes de las 18:00.</p>"
             "<ul><li>CPU: 92%</li><li>RAM: 78%</li></ul></body></html>")
    mbox.add(msg("alertas@monitoring.company.cl", "ALERTA: CPU > 90%",
                 html1, datetime(2024, 7, 20, 15, 30, tzinfo=timezone.utc),
                 "<html-001@test.local>", content_type="text/html", channel="Alerts"))

    html2 = ("<html><body><div><p>Estimado cliente,</p>"
             "<p>Su pedido #45892 ha sido <strong>despachado</strong>.</p>"
             "<p>Seguimiento: CL2024789456</p></div></body></html>")
    mbox.add(msg("despacho@tienda.online.cl", "Pedido #45892 despachado",
                 html2, datetime(2024, 8, 5, 11, 0, tzinfo=timezone.utc),
                 "<html-002@test.local>", content_type="text/html"))

    # --- GRUPO 4: Encoding mixto ---
    mbox.add(msg("francois@entreprise.fr", "Réunion à Paris",
                 "Bonjour, la réunion est prévue pour mardi prochain à 14h. "
                 "Merci de confirmer votre présence. Cordialement.",
                 datetime(2024, 3, 10, 8, 0, tzinfo=timezone.utc),
                 "<enc-latin-001@test.local>", charset="iso-8859-1"))

    mbox.add(msg("muller@firma.de", "Geschäftsbericht Q2",
                 "Sehr geehrte Damen und Herren, anbei der Geschäftsbericht Q2. "
                 "Die Umsätze sind um 15% gestiegen. Mit freundlichen Grüßen.",
                 datetime(2024, 4, 22, 14, 30, tzinfo=timezone.utc),
                 "<enc-latin-002@test.local>", charset="windows-1252"))

    # --- GRUPO 5: DEBEN SER DESCARTADOS ---

    # r01: email inválido
    mbox.add(msg("no-es-email", "Actor inválido",
                 "Este correo tiene un remitente que no es email válido, "
                 "debería ser descartado por r01_actor_email_valido.",
                 datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
                 "<bad-actor-001@test.local>"))

    # r02: timestamp futuro
    mbox.add(msg("futuro@example.com", "Correo del futuro",
                 "Este correo tiene fecha en el futuro lejano, debería ser "
                 "descartado por r02_timestamp_valido.",
                 datetime(2030, 12, 25, 0, 0, tzinfo=timezone.utc),
                 "<bad-ts-future@test.local>"))

    # r02: timestamp antes del 2000
    mbox.add(msg("antiguo@example.com", "Correo de 1999",
                 "Este correo tiene fecha anterior al 2000, debería ser "
                 "descartado por r02_timestamp_valido.",
                 datetime(1999, 6, 15, 12, 0, tzinfo=timezone.utc),
                 "<bad-ts-old@test.local>"))

    # r03: contenido muy corto (<= 10 chars)
    mbox.add(msg("corto@example.com", "Vacío", "Hola",
                 datetime(2024, 6, 1, 9, 0, tzinfo=timezone.utc),
                 "<bad-short-001@test.local>"))

    mbox.add(msg("corto2@example.com", "Solo espacios", "          ",
                 datetime(2024, 6, 2, 9, 0, tzinfo=timezone.utc),
                 "<bad-short-002@test.local>"))

    # r04: Message-ID duplicado (ambos se descartan)
    mbox.add(msg("dup1@example.com", "Original",
                 "Mensaje original con Message-ID que se repetirá en el siguiente. "
                 "Ambos deberían descartarse por r04.",
                 datetime(2024, 6, 10, 10, 0, tzinfo=timezone.utc),
                 "<duplicated-id@test.local>"))
    mbox.add(msg("dup2@example.com", "Duplicado",
                 "Mensaje duplicado que comparte Message-ID con el anterior. "
                 "Ambos deberían descartarse por r04.",
                 datetime(2024, 6, 11, 10, 0, tzinfo=timezone.utc),
                 "<duplicated-id@test.local>"))

    # r05: contenido vacío
    mbox.add(msg("vacio@example.com", "Body vacío", "",
                 datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                 "<bad-enc-001@test.local>"))

    mbox.close()

    box = mailbox.mbox(str(ruta))
    total = sum(1 for _ in box)
    box.close()
    print(f"Mbox generado: {ruta}")
    print(f"Total mensajes: {total}")
    print(f"Tamaño: {ruta.stat().st_size} bytes")
    print(f"  - 10 limpios variados")
    print(f"  - 20 seguimiento (volumen)")
    print(f"  - 2 HTML")
    print(f"  - 2 encoding mixto (ISO-8859-1, Windows-1252)")
    print(f"  - 1 actor inválido (r01)")
    print(f"  - 2 timestamp inválido (r02: futuro + antiguo)")
    print(f"  - 2 content corto/vacío (r03)")
    print(f"  - 2 Message-ID duplicado (r04)")
    print(f"  - 1 body vacío (r05)")
    print(f"  TOTAL ESPERADO VÁLIDOS: ~32 de {total}")


if __name__ == "__main__":
    generar()
