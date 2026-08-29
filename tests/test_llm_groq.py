"""Tests del cliente de Groq.

Lo central: que `texto_que_se_enviara` devuelva EXACTAMENTE lo que sale hacia Groq.
Esa funcion es la que hace verificable la promesa de privacidad — la interfaz se la muestra
a la persona antes de enviar. Si dejara de coincidir con lo que realmente se manda, la
promesa se volveria falsa sin que nadie lo note, que es la peor forma de romperla.
"""
from __future__ import annotations

import pytest

from app.graph.chats import Mensaje
from app.llm import groq as gq


def m(de, texto, mio=False):
    return Mensaje(de=de, texto=texto, cuando=None, es_mio=mio)


CONVERSACION = [
    m("Ana", "Hola, necesito el informe"),
    m("Yo", "Dale, te lo mando", mio=True),
    m("Ana", "Para cuando?"),
]


# ── La promesa de privacidad ───────────────────────────────────────────────
def test_lo_que_se_muestra_es_lo_que_se_envia(monkeypatch):
    enviado = {}

    class R:
        status_code, ok = 200, True
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": "Mañana"}}]}

    def post(url, headers=None, json=None, timeout=None):
        enviado["contenido"] = json["messages"][1]["content"]
        return R()

    monkeypatch.setattr(gq.requests, "post", post)
    previsto = gq.texto_que_se_enviara(CONVERSACION)
    gq.redactar_borrador("key", CONVERSACION)
    assert enviado["contenido"] == previsto, (
        "lo que se le muestra a la persona DEBE ser identico a lo que sale"
    )


def test_solo_se_envian_los_ultimos_mensajes():
    larga = [m("Ana", f"mensaje {i}") for i in range(40)]
    texto = gq.texto_que_se_enviara(larga)
    assert "mensaje 39" in texto
    assert "mensaje 0" not in texto, "no se manda la conversacion entera"
    assert texto.count("\n") < gq.MAX_MENSAJES_DE_CONTEXTO


def test_los_mensajes_propios_se_marcan_como_Yo():
    texto = gq.texto_que_se_enviara(CONVERSACION)
    assert "Yo: Dale, te lo mando" in texto
    assert "Ana: Para cuando?" in texto


def test_la_indicacion_de_la_persona_se_incluye_y_se_ve():
    texto = gq.texto_que_se_enviara(CONVERSACION, "responde que el viernes")
    assert "responde que el viernes" in texto


# ── El prompt tiene que prohibir inventar ──────────────────────────────────
def test_las_instrucciones_prohiben_inventar_datos():
    # Un borrador con una fecha o un monto inventado se envia con el nombre de la persona.
    assert "NO INVENTES DATOS" in gq.INSTRUCCIONES
    assert "[FALTA:" in gq.INSTRUCCIONES


# ── Fallar cerrado ─────────────────────────────────────────────────────────
def test_sin_clave_no_se_llama_a_groq():
    with pytest.raises(gq.ErrorDeGroq, match="clave"):
        gq.redactar_borrador("", CONVERSACION)


def test_sin_conversacion_no_se_redacta():
    with pytest.raises(gq.ErrorDeGroq, match="conversacion"):
        gq.redactar_borrador("key", [])


def test_una_clave_rechazada_lo_dice_claro(monkeypatch):
    class R:
        status_code, ok, text = 401, False, "invalid api key"
        def json(self): return {}
    monkeypatch.setattr(gq.requests, "post", lambda *a, **k: R())
    with pytest.raises(gq.ErrorDeGroq, match="rechazo la clave"):
        gq.redactar_borrador("mala", CONVERSACION)


def test_un_borrador_vacio_es_un_fallo_no_un_resultado(monkeypatch):
    # Devolver "" se veria como "el modelo no tenia nada que decir". Es un fallo.
    class R:
        status_code, ok, text = 200, True, ""
        def json(self): return {"choices": [{"message": {"content": "   "}}]}
    monkeypatch.setattr(gq.requests, "post", lambda *a, **k: R())
    with pytest.raises(gq.ErrorDeGroq, match="vacio"):
        gq.redactar_borrador("key", CONVERSACION)


def test_una_respuesta_con_forma_inesperada_se_rechaza(monkeypatch):
    class R:
        status_code, ok, text = 200, True, "{}"
        def json(self): return {"sin_choices": True}
    monkeypatch.setattr(gq.requests, "post", lambda *a, **k: R())
    with pytest.raises(gq.ErrorDeGroq, match="inesperada"):
        gq.redactar_borrador("key", CONVERSACION)


def test_la_temperatura_es_baja(monkeypatch):
    # Se busca fidelidad al contexto, no creatividad: un borrador creativo inventa.
    capturado = {}
    class R:
        status_code, ok, text = 200, True, ""
        def json(self): return {"choices": [{"message": {"content": "ok"}}]}
    def post(url, headers=None, json=None, timeout=None):
        capturado.update(json)
        return R()
    monkeypatch.setattr(gq.requests, "post", post)
    gq.redactar_borrador("key", CONVERSACION)
    assert capturado["temperature"] <= 0.5
