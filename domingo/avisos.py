"""
Avisos por correo del domingo de seguimiento y Excel del resumen del lunes.

Los constructores solo arman `Aviso` (sin red); `enviar` es el único punto de envío, para poder
agregar WhatsApp o SMS después sin tocar las reglas. Nunca imprime ni escribe contraseñas.
"""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from openpyxl import Workbook

PREFIJO = "[Sofía domingo]"
TIMEOUT_SMTP = 30
ESTADOS_PENDIENTES = ("pendiente", "en_curso", "sin_respuesta")

ETIQUETAS = {
    "pendiente": "pendiente", "en_curso": "en curso", "sin_respuesta": "sin respuesta",
    "a_tiempo": "a tiempo", "entregado": "entregado", "monitoreo": "monitoreo",
}


@dataclass
class Aviso:
    para: list[str]
    copia: list[str]
    asunto: str
    cuerpo: str
    adjunto: Path | None = None


# --------------------------------------------------------------------------- envío

def enviar(aviso, env, canal="correo", smtp=smtplib.SMTP):
    """
    Envía un aviso. Hoy solo existe el canal "correo" (STARTTLS). Regresa False, sin traza, si falta
    configuración o el envío falla; otro canal lanza NotImplementedError.
    """
    if canal != "correo":
        raise NotImplementedError(f"Canal de aviso no implementado: {canal!r}")

    host = env.get("SMTP_HOST")
    usuario = env.get("SMTP_USUARIO")
    clave = env.get("SMTP_PASSWORD")
    if not (host and usuario and clave):
        print("Aviso no enviado: falta SMTP_HOST, SMTP_USUARIO o SMTP_PASSWORD en .env.")
        return False
    try:
        puerto = int(env.get("SMTP_PUERTO") or 587)
    except ValueError:
        print("Aviso no enviado: SMTP_PUERTO no es un número.")
        return False
    if not aviso.para:
        print("Aviso no enviado: no tiene destinatarios.")
        return False

    mensaje = EmailMessage()
    mensaje["From"] = usuario
    mensaje["To"] = ", ".join(aviso.para)
    if aviso.copia:
        mensaje["Cc"] = ", ".join(aviso.copia)
    mensaje["Subject"] = aviso.asunto
    mensaje.set_content(aviso.cuerpo)
    try:
        if aviso.adjunto is not None:
            ruta = Path(aviso.adjunto)
            mensaje.add_attachment(
                ruta.read_bytes(), maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=ruta.name)
        with smtp(host, puerto, timeout=TIMEOUT_SMTP) as servidor:
            servidor.starttls()
            servidor.login(usuario, clave)
            servidor.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as e:
        # Solo el tipo de error: el texto de la excepción podría traer datos de la cuenta.
        print(f"Aviso no enviado ({type(e).__name__}): {aviso.asunto}")
        return False
    return True


# --------------------------------------------------------------------------- piezas de texto

def _asunto(domingo, texto):
    return f"{PREFIJO} {domingo} {texto}"


def _estado_de(estados, viaje):
    return estados.get(viaje["viaje"]) or {"estado": "pendiente", "intentos": 0, "historial": []}


def _cita_texto(viaje):
    prefijo = "antes de las" if viaje.get("tipo_cita") == "Día" else "a las"
    hora = viaje.get("limite") if viaje.get("tipo_cita") == "Día" else viaje.get("hora")
    return f"{viaje.get('fecha_cita', '')} {prefijo} {hora or viaje.get('limite', '')}"


def _que_dijo(estado):
    historial = estado.get("historial") or []
    dijo = historial[-1].get("hora_estimada_dicha") if historial else None
    motivo = historial[-1].get("motivo") if historial else None
    if not dijo and not motivo and not any(h.get("hablo_con_operador") for h in historial):
        return f"No contestó en {len(historial) or estado.get('intentos', 0)} llamadas"
    partes = [f"hora: {dijo}" if dijo else "hora: no la dio"]
    if motivo:
        partes.append(f"motivo: {motivo}")
    return "; ".join(partes)


def _conversacion(estado):
    historial = estado.get("historial") or []
    return (historial[-1].get("conversacion_id") if historial else None) or "(sin conversación)"


def _bloque_caso(viaje, estado):
    return "\n".join([
        f"Viaje {viaje['viaje']} - {viaje.get('linea', '')}",
        f"  Operador: {viaje.get('operador', '')} ({viaje.get('telefono', '')})",
        f"  Cliente: {viaje.get('cliente', '')}",
        f"  Cita: {_cita_texto(viaje)}",
        f"  Qué dijo: {_que_dijo(estado)}",
        f"  Llamadas hechas: {estado.get('intentos', 0)}",
        f"  Conversación: {_conversacion(estado)}",
    ])


def _por_persona(viajes):
    """Viajes agrupados por correo de monitoreo, en el orden de aparición."""
    grupos = {}
    for v in viajes:
        grupos.setdefault(v.get("correo_monitoreo", ""), []).append(v)
    return {correo: lista for correo, lista in grupos.items() if correo}


def _copia(correo_control):
    return [correo_control] if correo_control else []


# --------------------------------------------------------------------------- constructores

def avisos_de_casos(viajes, estados, correo_control, domingo=None):
    """Un aviso por persona de monitoreo con sus casos nuevos (aviso_pendiente); sin casos, no hay aviso."""
    lista = []
    for correo, suyos in _por_persona(viajes).items():
        casos = [v for v in suyos if _estado_de(estados, v).get("aviso_pendiente")]
        if not casos:
            continue
        bloques = [_bloque_caso(v, _estado_de(estados, v)) for v in casos]
        cuerpo = (f"Casos nuevos que pasan a monitoreo ({len(casos)}):\n\n" + "\n\n".join(bloques) + "\n")
        lista.append(Aviso([correo], _copia(correo_control),
                           f"{PREFIJO} {domingo + ' ' if domingo else ''}{len(casos)} caso(s) nuevo(s) en monitoreo",
                           cuerpo))
    return lista


def _conteos(viajes, estados):
    conteos = {"llamadas": 0, "a tiempo": 0, "entregado": 0, "monitoreo": 0, "pendientes": 0}
    for v in viajes:
        e = _estado_de(estados, v)
        conteos["llamadas"] += len(e.get("historial") or [])
        if e.get("estado") == "a_tiempo":
            conteos["a tiempo"] += 1
        elif e.get("estado") == "entregado":
            conteos["entregado"] += 1
        elif e.get("estado") == "monitoreo":
            conteos["monitoreo"] += 1
        elif e.get("estado") in ESTADOS_PENDIENTES:
            conteos["pendientes"] += 1
    return conteos


def aviso_de_control(domingo, momento, viajes, estados, correo_control, fallas):
    """Correo corto de control al terminar cada ronda; se arma siempre, aunque no haya casos."""
    lineas = [f"Ronda de las {momento} del domingo {domingo} terminada.", ""]
    lineas += [f"  {nombre}: {n}" for nombre, n in _conteos(viajes, estados).items()]
    if fallas:
        lineas += ["", "Fallas:"] + [f"  - {f}" for f in fallas]
    return Aviso(_copia(correo_control), [], _asunto(domingo, f"Control de la ronda de las {momento}"),
                 "\n".join(lineas) + "\n")


def aviso_de_aprobacion(domingo, aprobacion, correo_control):
    """Confirmación de que se aprobó la lista, con los viajes y el total de llamadas."""
    viajes = aprobacion["viajes"]
    cuando = aprobacion["cuando"].strftime("%Y-%m-%d %H:%M")
    lineas = [f"{aprobacion['quien']} aprobó la lista del domingo {domingo} ({cuando}).",
              f"Total de llamadas a hacer: {len(viajes)}", ""]
    for v in viajes:
        lineas.append(f"  {v['viaje']} - {v.get('operador', '')} - {v.get('cliente', '')} - {_cita_texto(v)}")
    return Aviso(_copia(correo_control), [], _asunto(domingo, f"Lista aprobada: {len(viajes)} llamadas"),
                 "\n".join(lineas) + "\n")


def aviso_sin_lista(domingo, correo_control):
    return Aviso(_copia(correo_control), [], _asunto(domingo, "No hay lista aprobada"),
                 f"No hay lista aprobada para el domingo {domingo}, por lo que no se hará ninguna llamada.\n")


def aviso_detenido(domingo, quien, cuando, correo_control):
    return Aviso(_copia(correo_control), [], _asunto(domingo, "Llamadas detenidas"),
                 f"{quien} detuvo las llamadas del domingo {domingo} a las {cuando.strftime('%H:%M')}. "
                 "No se hará ninguna llamada más hoy.\n")


def aviso_fallas_api(domingo, fallas, correo_control):
    lineas = [f"Fallas al llamar durante el domingo {domingo}:", ""] + [f"  - {f}" for f in fallas]
    return Aviso(_copia(correo_control), [], _asunto(domingo, "Fallas de la API de llamadas"),
                 "\n".join(lineas) + "\n")


def avisos_de_resumen(domingo, viajes, estados, correo_control, ruta_excel):
    """Resumen del lunes: uno por persona de monitoreo con sus viajes y uno a control con todos y el Excel."""
    lista = []
    for correo, suyos in _por_persona(viajes).items():
        lista.append(Aviso([correo], _copia(correo_control), _asunto(domingo, f"Resumen de {len(suyos)} viaje(s)"),
                           _cuerpo_resumen(domingo, suyos, estados)))
    escribir_excel_resumen(viajes, estados, ruta_excel)
    lista.append(Aviso(_copia(correo_control), [], _asunto(domingo, f"Resumen de {len(viajes)} viaje(s)"),
                       _cuerpo_resumen(domingo, viajes, estados), adjunto=Path(ruta_excel)))
    return lista


def _cuerpo_resumen(domingo, viajes, estados):
    lineas = [f"Resumen del domingo {domingo}.", ""]
    lineas += [f"  {nombre}: {n}" for nombre, n in _conteos(viajes, estados).items()]
    lineas.append("")
    for v in viajes:
        e = _estado_de(estados, v)
        lineas.append(f"{v['viaje']} - {v.get('operador', '')} ({v.get('telefono', '')}) - {_cita_texto(v)} - "
                      f"{ETIQUETAS.get(e.get('estado'), e.get('estado'))} - {e.get('intentos', 0)} llamada(s)")
        if e.get("estado") == "monitoreo":
            lineas.append(f"    Qué dijo: {_que_dijo(e)}")
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------- Excel

def escribir_excel_resumen(viajes, estados, ruta):
    """Excel del resumen: hoja Viajes (una fila por viaje) e Historial (una fila por llamada)."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Viajes"
    hoja.append(["Viaje", "Línea", "Operador", "Teléfono", "Cliente", "Destino", "Cita", "Monitoreo (correo)",
                 "Estado final", "Llamadas", "Qué dijo", "Última conversación"])
    historial = libro.create_sheet("Historial")
    historial.append(["Viaje", "Fecha de la llamada", "Decisión", "Habló con el operador", "Llega antes de la cita",
                      "Entrega realizada", "Hora que dijo", "Hora (HH:MM)", "Fecha estimada", "Motivo",
                      "Conversación"])
    for v in viajes:
        e = _estado_de(estados, v)
        hoja.append([v["viaje"], v.get("linea"), v.get("operador"), v.get("telefono"), v.get("cliente"),
                     v.get("destino"), _cita_texto(v), v.get("correo_monitoreo"),
                     ETIQUETAS.get(e.get("estado"), e.get("estado")), len(e.get("historial") or []),
                     _que_dijo(e) if e.get("historial") or e.get("intentos") else "", _conversacion(e)])
        for h in e.get("historial") or []:
            historial.append([v["viaje"], h.get("fecha"), h.get("decision"), _celda(h.get("hablo_con_operador")),
                              h.get("llega_antes_de_la_cita"), h.get("entrega_realizada"),
                              h.get("hora_estimada_dicha"), h.get("hora_estimada"), h.get("fecha_estimada"),
                              h.get("motivo"), h.get("conversacion_id")])
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
    return ruta


def _celda(valor):
    """Booleanos como Sí/No para el Excel; el resto tal cual."""
    if valor is True:
        return "Sí"
    if valor is False:
        return "No"
    return valor
