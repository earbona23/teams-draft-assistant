"""Configuracion de la aplicacion.

DOS TIPOS DE DATO, DOS TRATOS DISTINTOS
- Ajustes normales (ID de aplicacion, tenant, modelo) -> JSON en claro. No son secretos:
  un client ID de un cliente publico es informacion publica por diseno.
- La clave de Groq -> es un SECRETO y se guarda cifrada. Si el sistema no puede cifrar,
  la aplicacion AVISA y la mantiene solo en memoria; nunca la escribe en claro sin decirlo.

Escribir un secreto en texto plano "porque es una herramienta personal" es como se filtran
las claves: alguien sube la carpeta a un repositorio, hace un respaldo, o comparte la maquina.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable

CARPETA = pathlib.Path.home() / ".teams-draft-assistant"
ARCHIVO_AJUSTES = CARPETA / "config.json"
ARCHIVO_SECRETO = CARPETA / "groq.bin"


@dataclass
class Ajustes:
    client_id: str = ""
    tenant: str = "common"
    modelo: str = "llama-3.3-70b-versatile"
    mensajes_de_contexto: int = 15
    # No se guarda aca: vive cifrado aparte. El campo existe solo en memoria.
    groq_api_key: str = field(default="", repr=False)

    @property
    def configurado(self) -> bool:
        return bool(self.client_id and self.groq_api_key)

    def que_falta(self) -> list[str]:
        faltan = []
        if not self.client_id:
            faltan.append("el ID de aplicacion de Entra ID")
        if not self.groq_api_key:
            faltan.append("la clave de Groq")
        return faltan


def _persistencia_secreto(avisar: Callable[[str], None]):
    """Devuelve un objeto con save/load cifrado, o None si el sistema no puede cifrar."""
    try:
        from msal_extensions import (
            FilePersistenceWithDataProtection,
            KeychainPersistence,
            LibsecretPersistence,
        )

        CARPETA.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            return FilePersistenceWithDataProtection(str(ARCHIVO_SECRETO))
        if sys.platform == "darwin":
            return KeychainPersistence(str(ARCHIVO_SECRETO), "teams-draft-assistant", "groq")
        return LibsecretPersistence(
            str(ARCHIVO_SECRETO), schema_name="teams-draft-assistant", attributes={"k": "groq"}
        )
    except Exception as e:
        avisar(
            f"No se puede cifrar la clave de Groq en este sistema ({type(e).__name__}). "
            "Se va a pedir cada vez que abras la aplicacion. NO se guarda en texto plano."
        )
        return None


def cargar(avisar: Callable[[str], None] = print) -> Ajustes:
    ajustes = Ajustes()

    if ARCHIVO_AJUSTES.exists():
        try:
            datos = json.loads(ARCHIVO_AJUSTES.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            # Un config corrupto NO se ignora en silencio: se avisa y se arranca de cero,
            # porque si no la persona ve la app pidiendo configuracion sin entender por que.
            avisar(f"El archivo de configuracion no se pudo leer ({e}). Se empieza de cero.")
            datos = {}
        for campo in ("client_id", "tenant", "modelo", "mensajes_de_contexto"):
            if campo in datos:
                setattr(ajustes, campo, datos[campo])

    persistencia = _persistencia_secreto(avisar)
    if persistencia:
        try:
            contenido = persistencia.load()
            if contenido:
                ajustes.groq_api_key = json.loads(contenido).get("groq_api_key", "")
        except Exception:
            # No hay secreto guardado todavia, o no se pudo descifrar. No es un error:
            # significa que hay que pedirla. Se deja vacia.
            pass

    return ajustes


def guardar(ajustes: Ajustes, avisar: Callable[[str], None] = print) -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)

    publico = {k: v for k, v in asdict(ajustes).items() if k != "groq_api_key"}
    ARCHIVO_AJUSTES.write_text(
        json.dumps(publico, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if not ajustes.groq_api_key:
        return

    persistencia = _persistencia_secreto(avisar)
    if persistencia is None:
        avisar(
            "La clave de Groq NO se guardo: este sistema no ofrece almacenamiento cifrado. "
            "Habra que ingresarla en cada arranque."
        )
        return
    try:
        persistencia.save(json.dumps({"groq_api_key": ajustes.groq_api_key}))
    except Exception as e:
        avisar(f"No se pudo guardar la clave de Groq cifrada ({e}). No quedo guardada.")
