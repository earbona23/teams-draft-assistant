"""Lectura de chats de Teams via Microsoft Graph.

REGLA CENTRAL DE ESTE MODULO: SOLO CHATS 1:1
Eduard pidio explicitamente que no toque grupos, y el filtro se aplica en DOS lugares a
proposito —al listar y al leer mensajes— porque un solo filtro es un solo punto de fallo.
Si Graph cambiara el valor de `chatType` o devolviera algo inesperado, el segundo filtro
sigue de pie. Redactar un borrador para un canal de 40 personas es un error caro y silencioso.

FALLA CERRADO EN TODO: si una llamada no se puede completar, se lanza excepcion. Nunca se
devuelve una lista vacia ante un error, porque una lista vacia se lee como "no tenes chats"
—que es indistinguible de "no pude leerlos"— y esa confusion es justo la que hay que evitar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
TIEMPO_LIMITE = 30


class ErrorDeGraph(Exception):
    pass


@dataclass
class Chat:
    id: str
    con: str            # nombre de la otra persona
    correo: str
    ultimo_mensaje: str
    ultima_actividad: datetime | None
    lo_ultimo_es_mio: bool


@dataclass
class Mensaje:
    de: str
    texto: str
    cuando: datetime | None
    es_mio: bool


def _pedir(token: str, url: str, params: dict | None = None) -> dict:
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=TIEMPO_LIMITE,
        )
    except requests.RequestException as e:
        raise ErrorDeGraph(f"no se pudo contactar a Microsoft Graph: {e}") from e

    if r.status_code == 401:
        raise ErrorDeGraph("la sesion vencio o el token no es valido; volve a iniciar sesion")
    if r.status_code == 403:
        raise ErrorDeGraph(
            "Graph rechazo la peticion por permisos. Verifica que el registro tenga "
            "Chat.Read y ChatMessage.Send como permisos DELEGADOS y que hayas dado el "
            "consentimiento al iniciar sesion."
        )
    if r.status_code == 429:
        espera = r.headers.get("Retry-After", "?")
        raise ErrorDeGraph(f"Graph esta limitando las peticiones; reintentar en {espera}s")
    if not r.ok:
        raise ErrorDeGraph(f"Graph respondio {r.status_code}: {r.text[:200]}")

    try:
        return r.json()
    except ValueError as e:
        raise ErrorDeGraph(f"Graph devolvio algo que no es JSON: {r.text[:150]}") from e


def _fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _texto_plano(cuerpo: dict | None) -> str:
    """Graph devuelve HTML en muchos mensajes. Se limpia sin traer un parser entero."""
    if not cuerpo:
        return ""
    contenido = cuerpo.get("content") or ""
    if (cuerpo.get("contentType") or "").lower() != "html":
        return contenido.strip()
    import re

    sin_etiquetas = re.sub(r"<br\s*/?>", "\n", contenido, flags=re.I)
    sin_etiquetas = re.sub(r"</p\s*>", "\n", sin_etiquetas, flags=re.I)
    sin_etiquetas = re.sub(r"<[^>]+>", "", sin_etiquetas)
    for entidad, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        sin_etiquetas = sin_etiquetas.replace(entidad, char)
    return sin_etiquetas.strip()


def listar_chats_individuales(token: str, mi_correo: str, limite: int = 25) -> list[Chat]:
    """Devuelve solo chats 1:1, del mas reciente al mas antiguo."""
    datos = _pedir(
        token,
        f"{GRAPH}/me/chats",
        {
            "$expand": "members",
            "$top": str(min(limite * 2, 50)),  # se pide de mas porque se filtran grupos
            "$orderby": "lastMessagePreview/createdDateTime desc",
        },
    )

    salida: list[Chat] = []
    for c in datos.get("value", []):
        # FILTRO 1 de 2 — el tipo declarado por Graph.
        if c.get("chatType") != "oneOnOne":
            continue

        otros = [
            m for m in (c.get("members") or [])
            if (m.get("email") or "").lower() != (mi_correo or "").lower()
        ]
        # FILTRO 2 de 2 — la forma real del chat. Un 1:1 tiene exactamente UNA contraparte.
        # Si `chatType` mintiera o viniera raro, esto lo ataja igual.
        if len(otros) != 1:
            continue

        otro = otros[0]
        vista = c.get("lastMessagePreview") or {}
        de = ((vista.get("from") or {}).get("user") or {}).get("id")

        salida.append(
            Chat(
                id=c["id"],
                con=otro.get("displayName") or otro.get("email") or "?",
                correo=otro.get("email") or "",
                ultimo_mensaje=_texto_plano(vista.get("body"))[:160],
                ultima_actividad=_fecha(vista.get("createdDateTime")),
                lo_ultimo_es_mio=bool(de) and de == c.get("_mi_id"),
            )
        )
        if len(salida) >= limite:
            break

    return salida


def leer_conversacion(token: str, chat_id: str, mi_correo: str, cantidad: int = 15) -> list[Mensaje]:
    """Ultimos mensajes de un chat 1:1, en orden cronologico."""
    # FILTRO 2 (repetido a proposito): se vuelve a comprobar el tipo antes de leer contenido.
    # Nunca se leen mensajes de un chat sin haber confirmado que es 1:1 en ESTA llamada.
    meta = _pedir(token, f"{GRAPH}/chats/{chat_id}")
    if meta.get("chatType") != "oneOnOne":
        raise ErrorDeGraph(
            f"el chat solicitado es de tipo '{meta.get('chatType')}', no 1:1. "
            "Esta herramienta no lee chats grupales por diseno."
        )

    datos = _pedir(token, f"{GRAPH}/chats/{chat_id}/messages", {"$top": str(cantidad)})

    mensajes: list[Mensaje] = []
    for m in datos.get("value", []):
        if m.get("messageType") != "message":
            continue  # avisos de sistema: "fulano se unio", etc.
        texto = _texto_plano(m.get("body"))
        if not texto:
            continue
        remitente = ((m.get("from") or {}).get("user") or {})
        correo_remitente = (remitente.get("email") or "").lower()
        mensajes.append(
            Mensaje(
                de=remitente.get("displayName") or "?",
                texto=texto,
                cuando=_fecha(m.get("createdDateTime")),
                es_mio=correo_remitente == (mi_correo or "").lower(),
            )
        )

    mensajes.reverse()  # Graph los devuelve del mas nuevo al mas viejo
    return mensajes


def enviar_mensaje(token: str, chat_id: str, texto: str) -> None:
    """Envia el mensaje. Se llama SOLO desde el boton que aprieta la persona."""
    if not texto.strip():
        raise ErrorDeGraph("no se envia un mensaje vacio")
    try:
        r = requests.post(
            f"{GRAPH}/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"body": {"contentType": "text", "content": texto}},
            timeout=TIEMPO_LIMITE,
        )
    except requests.RequestException as e:
        raise ErrorDeGraph(f"no se pudo enviar: {e}") from e

    if not r.ok:
        raise ErrorDeGraph(f"Graph rechazo el envio ({r.status_code}): {r.text[:200]}")
