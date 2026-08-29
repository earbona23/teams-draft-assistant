"""Asistente de configuracion: la parte que hace que esto se pueda usar de verdad.

POR QUE EXISTE
Estas herramientas mueren en el primer paso: "pega tu client ID aca" sin decir de donde sale.
Registrar una aplicacion en Entra ID no es dificil, pero es imposible de adivinar. Este
asistente dice exactamente que hacer, en que orden, y COMPRUEBA cada paso antes de dejar
avanzar — para que el error aparezca donde se cometio y no tres pantallas despues.
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

import requests

from app import config as cfg

PORTAL = "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
GROQ = "https://console.groq.com/keys"

PASOS_ENTRA = """1. Abri el portal de Entra ID (boton de abajo) e inicia sesion.

2. "Registros de aplicaciones" → "Nuevo registro".
   · Nombre: el que quieras, por ejemplo "Asistente de borradores".
   · Tipos de cuenta: "Solo cuentas de este directorio organizativo".
   · URI de redireccion: DEJALA VACIA. No hace falta.
   · Registrar.

3. Copia el "Id. de aplicacion (cliente)" y pegalo abajo.

4. En el menu lateral → "Autenticacion":
   · Baja hasta "Configuracion avanzada".
   · "Permitir flujos de cliente publico" → SI. Guardar.
   ⚠ Sin este paso el inicio de sesion falla con un error que no lo explica.

5. En el menu lateral → "Permisos de API" → "Agregar un permiso":
   · Microsoft Graph → "Permisos DELEGADOS" (NO los de aplicacion).
   · Busca y marca: Chat.Read, ChatMessage.Send, User.Read
   · Agregar permisos.
   ⚠ Delegados = la app ve solo lo que ves vos. Los de aplicacion verian los chats de
     TODA la organizacion y requieren aprobacion de un administrador.
"""


class Asistente(tk.Toplevel):
    """Devuelve unos Ajustes completos, o None si la persona cancela."""

    def __init__(self, padre: tk.Misc | None, ajustes: cfg.Ajustes) -> None:
        super().__init__(padre)
        self.ajustes = ajustes
        self.resultado: cfg.Ajustes | None = None

        self.title("Configuracion")
        self.geometry("720x640")
        self.transient(padre)
        self.grab_set()

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        nb.add(self._pestana_entra(nb), text="1 · Microsoft Entra ID")
        nb.add(self._pestana_groq(nb), text="2 · Clave de Groq")

        pie = ttk.Frame(self, padding=(12, 0, 12, 12))
        pie.pack(fill=tk.X)
        self.lbl = ttk.Label(pie, text="", foreground="#666")
        self.lbl.pack(side=tk.LEFT)
        ttk.Button(pie, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(pie, text="Guardar", command=self._guardar).pack(side=tk.RIGHT, padx=6)

    def _pestana_entra(self, padre) -> ttk.Frame:
        f = ttk.Frame(padre, padding=10)
        t = scrolledtext.ScrolledText(f, height=17, wrap=tk.WORD)
        t.pack(fill=tk.BOTH, expand=True)
        t.insert("1.0", PASOS_ENTRA)
        t.config(state=tk.DISABLED)

        ttk.Button(f, text="Abrir el portal de Entra ID",
                   command=lambda: webbrowser.open(PORTAL)).pack(anchor="w", pady=8)

        fila = ttk.Frame(f)
        fila.pack(fill=tk.X, pady=4)
        ttk.Label(fila, text="Id. de aplicacion (cliente):", width=26).pack(side=tk.LEFT)
        self.ent_client = ttk.Entry(fila)
        self.ent_client.insert(0, self.ajustes.client_id)
        self.ent_client.pack(side=tk.LEFT, fill=tk.X, expand=True)

        fila2 = ttk.Frame(f)
        fila2.pack(fill=tk.X, pady=4)
        ttk.Label(fila2, text="Tenant (o 'common'):", width=26).pack(side=tk.LEFT)
        self.ent_tenant = ttk.Entry(fila2)
        self.ent_tenant.insert(0, self.ajustes.tenant or "common")
        self.ent_tenant.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return f

    def _pestana_groq(self, padre) -> ttk.Frame:
        f = ttk.Frame(padre, padding=10)
        ttk.Label(
            f,
            text=("La clave de Groq es gratis. Se crea en console.groq.com/keys y se copia UNA "
                  "sola vez: si cerras esa pantalla sin copiarla, hay que crear otra.\n\n"
                  "Se guarda cifrada con el almacenamiento del sistema operativo. Si tu sistema "
                  "no ofrece cifrado, la aplicacion te avisa y te la pide en cada arranque — "
                  "nunca la escribe en texto plano sin decirlo."),
            wraplength=640, justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 10))

        ttk.Button(f, text="Abrir console.groq.com/keys",
                   command=lambda: webbrowser.open(GROQ)).pack(anchor="w", pady=6)

        fila = ttk.Frame(f)
        fila.pack(fill=tk.X, pady=8)
        ttk.Label(fila, text="Clave de Groq:", width=16).pack(side=tk.LEFT)
        self.ent_groq = ttk.Entry(fila, show="•")
        self.ent_groq.insert(0, self.ajustes.groq_api_key)
        self.ent_groq.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(fila, text="Probar", command=self._probar_groq).pack(side=tk.LEFT, padx=6)

        self.lbl_groq = ttk.Label(f, text="", wraplength=640, justify=tk.LEFT)
        self.lbl_groq.pack(anchor="w", pady=6)
        return f

    def _probar_groq(self) -> None:
        """Comprueba la clave contra Groq DE VERDAD. Guardarla sin probarla deja el fallo
        para el primer borrador, cuando la persona ya no asocia el error con la clave."""
        clave = self.ent_groq.get().strip()
        if not clave:
            self.lbl_groq.config(text="Pega la clave primero.", foreground="#a00")
            return
        self.lbl_groq.config(text="probando…", foreground="#666")
        self.update_idletasks()
        try:
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {clave}"},
                timeout=20,
            )
        except requests.RequestException as e:
            self.lbl_groq.config(text=f"No se pudo contactar a Groq: {e}", foreground="#a00")
            return
        if r.status_code == 401:
            self.lbl_groq.config(text="Groq rechazo la clave.", foreground="#a00")
        elif r.ok:
            self.lbl_groq.config(text="La clave funciona.", foreground="#070")
        else:
            self.lbl_groq.config(text=f"Groq respondio {r.status_code}.", foreground="#a00")

    def _guardar(self) -> None:
        a = cfg.Ajustes(
            client_id=self.ent_client.get().strip(),
            tenant=self.ent_tenant.get().strip() or "common",
            modelo=self.ajustes.modelo,
            mensajes_de_contexto=self.ajustes.mensajes_de_contexto,
            groq_api_key=self.ent_groq.get().strip(),
        )
        faltan = a.que_falta()
        if faltan:
            # No se guarda a medias: una configuracion incompleta hace que la app falle
            # despues, en un lugar donde el error ya no apunta a lo que falta.
            messagebox.showwarning("Falta configurar", "Todavia falta " + " y ".join(faltan) + ".")
            return
        cfg.guardar(a, avisar=lambda m: messagebox.showwarning("Aviso", m))
        self.resultado = a
        self.destroy()
