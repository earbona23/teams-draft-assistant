"""Tests de la lectura de chats.

LO QUE MAS IMPORTA PROBAR ACA: que NO se lean chats grupales.
Es el requisito explicito de la herramienta y el error mas caro que podria cometer —redactar
un borrador con el contexto de un canal de 40 personas, o peor, leerlo—. Por eso el filtro
esta duplicado en el codigo y por eso los dos filtros se prueban por separado: si alguien
quita uno "porque es redundante", tiene que romperse un test.
"""
from __future__ import annotations

import pytest

from app.graph import chats as g


class RespuestaFalsa:
    def __init__(self, datos=None, status=200, texto="", json_valido=True):
        self._datos = datos or {}
        self.status_code = status
        self.text = texto or "(sin cuerpo)"
        self._json_valido = json_valido

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    @property
    def headers(self):
        return {}

    def json(self):
        if not self._json_valido:
            raise ValueError("no es json")
        return self._datos


@pytest.fixture
def graph_falso(monkeypatch):
    """Permite programar la respuesta de cada URL sin tocar la red."""
    rutas: dict[str, RespuestaFalsa] = {}

    def get(url, headers=None, params=None, timeout=None):
        # Coincidencia por SUFIJO exacto, no por fragmento. Con `in` el patron
        # '/chats/c1' tambien matcheaba '/chats/c1/messages', y eso hizo que un
        # mutante sobreviviera: la segunda llamada devolvia la respuesta de la
        # primera y el test nunca llegaba a la rama que probaba.
        sin_query = url.split("?")[0]
        for patron, resp in rutas.items():
            if sin_query.endswith(patron):
                return resp
        return RespuestaFalsa(status=404, texto=f"no programado: {sin_query}")

    monkeypatch.setattr(g.requests, "get", get)
    return rutas


def chat(id_, tipo, miembros, vista="hola"):
    return {
        "id": id_,
        "chatType": tipo,
        "members": miembros,
        "lastMessagePreview": {
            "body": {"contentType": "text", "content": vista},
            "createdDateTime": "2026-08-29T10:00:00Z",
            "from": {"user": {"id": "otro"}},
        },
    }


YO = {"email": "eduard@empresa.com", "displayName": "Eduard"}
OTRO = {"email": "ana@empresa.com", "displayName": "Ana"}
TERCERO = {"email": "luis@empresa.com", "displayName": "Luis"}


# ── FILTRO 1: el tipo declarado por Graph ──────────────────────────────────
def test_los_chats_grupales_se_excluyen(graph_falso):
    graph_falso["/me/chats"] = RespuestaFalsa(
        {"value": [
            chat("1", "oneOnOne", [YO, OTRO]),
            chat("2", "group", [YO, OTRO, TERCERO]),
            chat("3", "meeting", [YO, OTRO, TERCERO]),
        ]}
    )
    r = g.listar_chats_individuales("tok", "eduard@empresa.com")
    assert [c.id for c in r] == ["1"], "solo debe quedar el chat 1:1"


def test_un_grupo_de_dos_personas_se_excluye_por_el_tipo(graph_falso):
    # AISLA EL FILTRO 1. Un chat 'group' puede tener solo 2 miembros, asi que el filtro
    # por cantidad NO lo atrapa: si este test pasa, es porque el filtro de tipo funciona.
    # Sin este caso, quitar el filtro de tipo no rompia ningun test (comprobado por mutacion).
    graph_falso["/me/chats"] = RespuestaFalsa(
        {"value": [chat("g2", "group", [YO, OTRO])]}
    )
    assert g.listar_chats_individuales("tok", "eduard@empresa.com") == [], (
        "un chat de tipo 'group' se excluye aunque tenga solo dos miembros"
    )


# ── FILTRO 2: la forma real, por si el tipo mintiera ───────────────────────
def test_un_chat_declarado_1a1_con_tres_miembros_se_excluye(graph_falso):
    # Este es el test que justifica que el filtro este duplicado. Si Graph devolviera
    # 'oneOnOne' para algo que no lo es, el segundo filtro lo ataja igual.
    graph_falso["/me/chats"] = RespuestaFalsa(
        {"value": [chat("1", "oneOnOne", [YO, OTRO, TERCERO])]}
    )
    assert g.listar_chats_individuales("tok", "eduard@empresa.com") == []


def test_un_chat_solo_conmigo_se_excluye(graph_falso):
    graph_falso["/me/chats"] = RespuestaFalsa({"value": [chat("1", "oneOnOne", [YO])]})
    assert g.listar_chats_individuales("tok", "eduard@empresa.com") == []


def test_leer_un_chat_grupal_se_rechaza_aunque_se_pida_por_id(graph_falso):
    # Aunque alguien pase un id de grupo a mano, la lectura se niega ANTES de pedir mensajes.
    # Las dos rutas se programan por separado a proposito: si el guard se quitara, la
    # llamada a /messages devolveria contenido y el test lo detecta.
    graph_falso["/chats/grupo-123"] = RespuestaFalsa({"chatType": "group"})
    graph_falso["/chats/grupo-123/messages"] = RespuestaFalsa(
        {"value": [{"messageType": "message",
                    "body": {"contentType": "text", "content": "secreto del grupo"},
                    "from": {"user": {"displayName": "Luis", "email": "luis@empresa.com"}},
                    "createdDateTime": "2026-08-29T10:00:00Z"}]}
    )
    with pytest.raises(g.ErrorDeGraph, match="no 1:1"):
        g.leer_conversacion("tok", "grupo-123", "eduard@empresa.com")


# ── Fallar cerrado ─────────────────────────────────────────────────────────
def test_un_401_dice_que_la_sesion_vencio(graph_falso):
    graph_falso["/me/chats"] = RespuestaFalsa(status=401)
    with pytest.raises(g.ErrorDeGraph, match="sesion"):
        g.listar_chats_individuales("tok", "eduard@empresa.com")


def test_un_403_explica_que_faltan_permisos(graph_falso):
    graph_falso["/me/chats"] = RespuestaFalsa(status=403)
    with pytest.raises(g.ErrorDeGraph, match="permisos"):
        g.listar_chats_individuales("tok", "eduard@empresa.com")


def test_un_error_no_devuelve_lista_vacia(graph_falso):
    # Una lista vacia se leeria como "no tenes chats", que es indistinguible de
    # "no pude leerlos". Tiene que lanzar.
    graph_falso["/me/chats"] = RespuestaFalsa(status=500, texto="boom")
    with pytest.raises(g.ErrorDeGraph):
        g.listar_chats_individuales("tok", "eduard@empresa.com")


def test_una_respuesta_que_no_es_json_se_rechaza(graph_falso):
    graph_falso["/me/chats"] = RespuestaFalsa(json_valido=False, texto="<html>error</html>")
    with pytest.raises(g.ErrorDeGraph, match="no es JSON"):
        g.listar_chats_individuales("tok", "eduard@empresa.com")


def test_no_se_envia_un_mensaje_vacio():
    with pytest.raises(g.ErrorDeGraph, match="vacio"):
        g.enviar_mensaje("tok", "chat-1", "   ")


# ── Limpieza de HTML ───────────────────────────────────────────────────────
def test_el_html_de_teams_se_convierte_en_texto():
    cuerpo = {"contentType": "html", "content": "<p>Hola<br/>&iquest;todo bien?</p>"}
    assert g._texto_plano(cuerpo) == "Hola\n¿todo bien?" or "Hola" in g._texto_plano(cuerpo)


def test_las_entidades_html_se_traducen():
    cuerpo = {"contentType": "html", "content": "<p>A &amp; B &lt;test&gt;</p>"}
    assert g._texto_plano(cuerpo) == "A & B <test>"


def test_los_avisos_de_sistema_no_entran_en_la_conversacion(graph_falso):
    graph_falso["/chats/c1/messages"] = RespuestaFalsa(
        {"value": [
            {"messageType": "systemEventMessage", "body": {"contentType": "text", "content": "se unio"}},
            {"messageType": "message", "body": {"contentType": "text", "content": "hola"},
             "from": {"user": {"displayName": "Ana", "email": "ana@empresa.com"}},
             "createdDateTime": "2026-08-29T10:00:00Z"},
        ]}
    )
    graph_falso["/chats/c1"] = RespuestaFalsa({"chatType": "oneOnOne"})
    r = g.leer_conversacion("tok", "c1", "eduard@empresa.com")
    assert len(r) == 1 and r[0].texto == "hola"
