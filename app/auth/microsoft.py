"""Autenticacion con Microsoft mediante el flujo de codigo de dispositivo.

POR QUE CODIGO DE DISPOSITIVO Y NO REDIRECCION AL NAVEGADOR
El flujo con redireccion exige registrar una URI de redireccion exacta en Entra ID, y cualquier
diferencia —el puerto, la barra final— falla con un error que no explica nada. Es donde se traba
la mayoria de la gente que intenta esto por primera vez.

El flujo de dispositivo no necesita URI: muestra un codigo, lo pegas en el navegador y listo.
La contrapartida es que el registro debe permitir "flujos de cliente publico", que es una casilla
en el portal y esta en la guia de docs/setup.md.

POR QUE PERMISOS DELEGADOS Y NO DE APLICACION
Delegados = la app actua CON TU SESION y solo puede ver lo que vos podes ver. De aplicacion =
la app puede leer los chats de TODO el tenant, requiere aprobacion de un administrador, y si
alguien roba ese token tiene acceso a la organizacion entera.
Para una herramienta personal, pedir permisos de aplicacion seria desproporcionado y peligroso.

EL TOKEN NO SE GUARDA EN TEXTO PLANO
Se usa el cache cifrado de msal-extensions: DPAPI en Windows, Keychain en macOS, libsecret en
Linux. Si el cifrado no esta disponible, la app AVISA y sigue en memoria —el token se pierde al
cerrar— en vez de escribirlo en claro sin decirlo.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Callable

import msal

# El minimo que permite leer los chats propios y responderlos.
# NO se pide Chat.ReadWrite.All ni nada .All: eso alcanzaria a toda la organizacion.
ALCANCES = ["Chat.Read", "ChatMessage.Send", "User.Read"]

AUTORIDAD = "https://login.microsoftonline.com/{tenant}"


@dataclass
class Sesion:
    token: str
    nombre: str
    correo: str


class ErrorDeAutenticacion(Exception):
    """Se lanza cuando la autenticacion no se pudo completar. Nunca se devuelve None:
    un None se propagaria como 'no hay sesion' y la app lo leeria como 'todavia no inicio',
    ocultando el motivo real del fallo."""


def _construir_cache(ruta: pathlib.Path, avisar: Callable[[str], None]):
    """Cache de token cifrado. Si no se puede cifrar, se AVISA y se usa memoria."""
    try:
        from msal_extensions import (
            FilePersistenceWithDataProtection,
            KeychainPersistence,
            LibsecretPersistence,
            PersistedTokenCache,
        )

        ruta.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            persistencia = FilePersistenceWithDataProtection(str(ruta))
        elif sys.platform == "darwin":
            persistencia = KeychainPersistence(str(ruta), "teams-draft-assistant", "token")
        else:
            persistencia = LibsecretPersistence(
                str(ruta), schema_name="teams-draft-assistant", attributes={"app": "tda"}
            )
        return PersistedTokenCache(persistencia)
    except Exception as e:
        avisar(
            "No se pudo cifrar el almacenamiento del token en este sistema "
            f"({type(e).__name__}). La sesion se mantiene SOLO EN MEMORIA y se pierde al "
            "cerrar la aplicacion. El token NO se guarda en disco sin cifrar."
        )
        return msal.SerializableTokenCache()


class AutenticadorMicrosoft:
    """Envuelve MSAL. Se inyecta la app de MSAL para poder probar sin un tenant real."""

    def __init__(
        self,
        client_id: str,
        tenant: str = "common",
        ruta_cache: pathlib.Path | None = None,
        avisar: Callable[[str], None] = print,
        _app=None,
    ) -> None:
        if not client_id:
            raise ErrorDeAutenticacion(
                "Falta el ID de aplicacion. Se obtiene registrando una aplicacion en Entra ID; "
                "el asistente de configuracion te guia paso a paso."
            )
        self.avisar = avisar
        ruta = ruta_cache or pathlib.Path.home() / ".teams-draft-assistant" / "token.bin"
        self._cache = _construir_cache(ruta, avisar)
        self._app = _app or msal.PublicClientApplication(
            client_id,
            authority=AUTORIDAD.format(tenant=tenant),
            token_cache=self._cache,
        )

    def sesion_guardada(self) -> Sesion | None:
        """Intenta reusar un token del cache. Devuelve None solo si NO hay sesion previa."""
        cuentas = self._app.get_accounts()
        if not cuentas:
            return None
        r = self._app.acquire_token_silent(ALCANCES, account=cuentas[0])
        if not r or "access_token" not in r:
            # El cache tenia una cuenta pero el token no se pudo renovar. Eso NO es
            # "no hay sesion": es una sesion vencida, y hay que decirlo distinto.
            self.avisar("La sesion guardada vencio. Hay que iniciar sesion de nuevo.")
            return None
        c = cuentas[0]
        return Sesion(
            token=r["access_token"],
            nombre=c.get("username", "?"),
            correo=c.get("username", "?"),
        )

    def iniciar_sesion(self, mostrar_codigo: Callable[[str, str], None]) -> Sesion:
        """Arranca el flujo de dispositivo. `mostrar_codigo(codigo, url)` lo muestra en la UI."""
        flujo = self._app.initiate_device_flow(scopes=ALCANCES)
        if "user_code" not in flujo:
            # El error mas comun aca es que el registro no tiene habilitados los flujos de
            # cliente publico. Se dice explicitamente porque el mensaje de Microsoft no lo aclara.
            raise ErrorDeAutenticacion(
                "No se pudo iniciar el flujo de dispositivo. La causa mas frecuente es que el "
                "registro de la aplicacion no tenga habilitado 'Allow public client flows'. "
                f"Detalle: {flujo.get('error_description', flujo)}"
            )

        mostrar_codigo(flujo["user_code"], flujo["verification_uri"])
        r = self._app.acquire_token_by_device_flow(flujo)

        if "access_token" not in r:
            raise ErrorDeAutenticacion(
                f"La autenticacion no se completo: "
                f"{r.get('error_description') or r.get('error') or r}"
            )

        reclamos = r.get("id_token_claims") or {}
        correo = reclamos.get("preferred_username") or reclamos.get("upn") or "?"
        return Sesion(
            token=r["access_token"],
            nombre=reclamos.get("name") or correo,
            correo=correo,
        )

    def cerrar_sesion(self) -> None:
        for c in self._app.get_accounts():
            self._app.remove_account(c)
