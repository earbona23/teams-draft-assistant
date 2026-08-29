"""Cliente de Groq para redactar borradores.

QUE SE MANDA Y QUE NO — la decision de privacidad
Solo se envia el chat que la persona ABRIO, y solo los ultimos mensajes. No hay recorrido
automatico de conversaciones ni envio en segundo plano: cada llamada la origina un clic.

Ademas `texto_que_se_enviara()` devuelve exactamente lo que va a salir, para que la interfaz
pueda mostrarselo ANTES de mandarlo. Esa funcion existe para que la promesa "solo se manda lo
que elegis" sea verificable por el usuario y no una afirmacion del README.

EL BORRADOR ES UN BORRADOR
El prompt pide explicitamente que NO invente datos, y que cuando falte informacion lo diga en
vez de rellenar. Un asistente de borradores que inventa un compromiso —una fecha, un precio, un
"si, lo hago"— es peor que no tener asistente, porque la persona lo firma con su nombre.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

API = "https://api.groq.com/openai/v1/chat/completions"
MODELO_POR_DEFECTO = "llama-3.3-70b-versatile"
TIEMPO_LIMITE = 60
MAX_MENSAJES_DE_CONTEXTO = 15


class ErrorDeGroq(Exception):
    pass


@dataclass
class Borrador:
    texto: str
    modelo: str


INSTRUCCIONES = """Sos un asistente que redacta BORRADORES de respuesta para un chat de trabajo.
La persona va a leer tu borrador, lo va a editar si quiere, y lo va a enviar ella misma.

Reglas:
- Escribi en el mismo idioma y registro que la conversacion. Si la charla es informal, no
  contestes acartonado; si es formal, no seas coloquial.
- Se breve. Un chat no es un correo.
- NO INVENTES DATOS. Si para responder hace falta un dato que no esta en la conversacion
  —una fecha, un monto, un nombre, un estado— NO lo rellenes: dejalo marcado como [FALTA: ...]
  para que la persona lo complete. Un borrador con un dato inventado se envia con su nombre.
- No prometas nada en nombre de la persona que la conversacion no respalde.
- No agregues saludos ni firmas si la conversacion no los usa.
- Devolve UNICAMENTE el texto del borrador. Sin comillas, sin explicaciones, sin "Aqui tienes:".
"""


def texto_que_se_enviara(mensajes, instruccion_extra: str = "") -> str:
    """Devuelve, literal, lo que se le va a mandar a Groq. Para mostrarselo a la persona ANTES.

    Existe para que la promesa de privacidad sea comprobable: la interfaz muestra esto y la
    persona decide. Sin esta funcion, "solo se manda lo que elegis" seria una afirmacion sin
    forma de verificarla.
    """
    recientes = mensajes[-MAX_MENSAJES_DE_CONTEXTO:]
    lineas = [f"{'Yo' if m.es_mio else m.de}: {m.texto}" for m in recientes]
    cuerpo = "\n".join(lineas)
    if instruccion_extra.strip():
        cuerpo += f"\n\n[Indicacion de la persona para este borrador: {instruccion_extra.strip()}]"
    return cuerpo


def redactar_borrador(
    api_key: str,
    mensajes,
    instruccion_extra: str = "",
    modelo: str = MODELO_POR_DEFECTO,
) -> Borrador:
    if not api_key or not api_key.strip():
        raise ErrorDeGroq(
            "Falta la clave de Groq. Se obtiene gratis en console.groq.com y se pega en "
            "la configuracion de la aplicacion."
        )
    if not mensajes:
        raise ErrorDeGroq("no hay conversacion de la cual redactar un borrador")

    contenido = texto_que_se_enviara(mensajes, instruccion_extra)

    try:
        r = requests.post(
            API,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": modelo,
                "temperature": 0.4,   # bajo a proposito: se busca fidelidad al contexto, no creatividad
                "max_tokens": 500,
                "messages": [
                    {"role": "system", "content": INSTRUCCIONES},
                    {"role": "user", "content": contenido},
                ],
            },
            timeout=TIEMPO_LIMITE,
        )
    except requests.RequestException as e:
        raise ErrorDeGroq(f"no se pudo contactar a Groq: {e}") from e

    if r.status_code == 401:
        raise ErrorDeGroq("Groq rechazo la clave. Verificala en console.groq.com.")
    if r.status_code == 429:
        raise ErrorDeGroq("Groq esta limitando las peticiones. Esperar un momento y reintentar.")
    if not r.ok:
        raise ErrorDeGroq(f"Groq respondio {r.status_code}: {r.text[:200]}")

    try:
        datos = r.json()
        texto = datos["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError) as e:
        raise ErrorDeGroq(f"respuesta de Groq inesperada: {r.text[:200]}") from e

    if not texto or not texto.strip():
        # Devolver un borrador vacio se veria como "el modelo no tenia nada que decir".
        # Es un fallo, y hay que nombrarlo.
        raise ErrorDeGroq("Groq devolvio un borrador vacio")

    return Borrador(texto=texto.strip(), modelo=modelo)
