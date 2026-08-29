"""Ventana principal: chats a la izquierda, conversacion arriba, borrador abajo.

LA DECISION QUE ORDENA TODA LA INTERFAZ
El boton de enviar y el de generar borrador estan SEPARADOS y nunca se encadenan. Generar
no envia. Enviar no genera. No hay ningun camino en el que un texto salga sin que la persona
lo haya leido y apretado "Enviar".

Y hay un boton, "Ver que se envia a Groq", que muestra el texto exacto que va a salir. Existe
para que la promesa de privacidad sea VERIFICABLE por la persona y no una linea del README.
Lo que muestra sale de la misma funcion que arma el envio real, asi que no pueden divergir.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from app import config as cfg
from app.auth.microsoft import AutenticadorMicrosoft, ErrorDeAutenticacion
from app.graph import chats as graph
from app.llm import groq


class Ventana(tk.Tk):
    def __init__(self, ajustes: cfg.Ajustes) -> None:
        super().__init__()
        self.ajustes = ajustes
        self.sesion = None
        self.chats: list[graph.Chat] = []
        self.conversacion: list[graph.Mensaje] = []
        self.chat_actual: graph.Chat | None = None

        self.title("Asistente de borradores para Teams")
        self.geometry("1000x680")
        self.minsize(820, 560)

        self._construir()
        self.after(200, self._iniciar_sesion_si_hay)

    # ── Construccion ──────────────────────────────────────────────────────
    def _construir(self) -> None:
        barra = ttk.Frame(self, padding=(10, 8))
        barra.pack(fill=tk.X)
        self.lbl_sesion = ttk.Label(barra, text="Sin sesion iniciada")
        self.lbl_sesion.pack(side=tk.LEFT)
        ttk.Button(barra, text="Iniciar sesion", command=self._iniciar_sesion).pack(side=tk.RIGHT)
        ttk.Button(barra, text="Actualizar chats", command=self._cargar_chats).pack(
            side=tk.RIGHT, padx=6
        )

        cuerpo = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        cuerpo.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Izquierda: chats 1:1
        izq = ttk.Frame(cuerpo)
        ttk.Label(izq, text="Chats individuales", font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(
            izq,
            text="Los chats de grupo no se muestran ni se leen.",
            foreground="#666",
            wraplength=230,
        ).pack(anchor="w", pady=(0, 6))
        self.lista = tk.Listbox(izq, exportselection=False, activestyle="none")
        self.lista.pack(fill=tk.BOTH, expand=True)
        self.lista.bind("<<ListboxSelect>>", self._al_elegir_chat)
        cuerpo.add(izq, weight=1)

        # Derecha: conversacion + borrador
        der = ttk.Frame(cuerpo)
        ttk.Label(der, text="Conversacion", font=("", 10, "bold")).pack(anchor="w")
        self.txt_conv = scrolledtext.ScrolledText(der, height=14, wrap=tk.WORD, state=tk.DISABLED)
        self.txt_conv.pack(fill=tk.BOTH, expand=True, pady=(2, 8))

        fila = ttk.Frame(der)
        fila.pack(fill=tk.X)
        ttk.Label(fila, text="Indicacion (opcional):").pack(side=tk.LEFT)
        self.ent_indicacion = ttk.Entry(fila)
        self.ent_indicacion.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(fila, text="Ver que se envia a Groq", command=self._ver_envio).pack(side=tk.LEFT)

        ttk.Label(der, text="Borrador — revisalo antes de enviar", font=("", 10, "bold")).pack(
            anchor="w", pady=(10, 0)
        )
        self.txt_borrador = scrolledtext.ScrolledText(der, height=8, wrap=tk.WORD)
        self.txt_borrador.pack(fill=tk.BOTH, expand=True, pady=(2, 8))

        acciones = ttk.Frame(der)
        acciones.pack(fill=tk.X)
        self.btn_generar = ttk.Button(acciones, text="Generar borrador", command=self._generar)
        self.btn_generar.pack(side=tk.LEFT)
        # Enviar esta SEPARADO y no se encadena con generar. Nunca hay envio automatico.
        self.btn_enviar = ttk.Button(acciones, text="Enviar a Teams", command=self._enviar)
        self.btn_enviar.pack(side=tk.LEFT, padx=8)
        self.lbl_estado = ttk.Label(acciones, text="", foreground="#666")
        self.lbl_estado.pack(side=tk.LEFT, padx=10)

        cuerpo.add(der, weight=3)

    # ── Utilidades ────────────────────────────────────────────────────────
    def _estado(self, texto: str) -> None:
        self.lbl_estado.config(text=texto)
        self.update_idletasks()

    def _en_hilo(self, trabajo, al_terminar) -> None:
        """Corre trabajo() fuera del hilo de la interfaz para que no se congele.

        El resultado vuelve por `after`, que es la unica forma segura de tocar widgets
        de Tkinter desde otro hilo.
        """

        def correr():
            try:
                r = trabajo()
                self.after(0, lambda: al_terminar(r, None))
            except Exception as e:  # se propaga el error a la UI, nunca se traga
                self.after(0, lambda: al_terminar(None, e))

        threading.Thread(target=correr, daemon=True).start()

    # ── Sesion ────────────────────────────────────────────────────────────
    def _autenticador(self) -> AutenticadorMicrosoft:
        return AutenticadorMicrosoft(
            client_id=self.ajustes.client_id,
            tenant=self.ajustes.tenant,
            avisar=lambda m: messagebox.showwarning("Aviso", m),
        )

    def _iniciar_sesion_si_hay(self) -> None:
        try:
            s = self._autenticador().sesion_guardada()
        except ErrorDeAutenticacion as e:
            self._estado(str(e)[:90])
            return
        if s:
            self.sesion = s
            self.lbl_sesion.config(text=f"Sesion: {s.nombre}")
            self._cargar_chats()

    def _iniciar_sesion(self) -> None:
        def mostrar(codigo: str, url: str) -> None:
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Iniciar sesion",
                    f"1. Abri {url}\n2. Escribi este codigo:\n\n        {codigo}\n\n"
                    "3. Volve aca cuando termines. La ventana se actualiza sola.",
                ),
            )

        self._estado("esperando que completes el inicio de sesion…")
        self._en_hilo(
            lambda: self._autenticador().iniciar_sesion(mostrar),
            self._sesion_lista,
        )

    def _sesion_lista(self, sesion, error) -> None:
        if error:
            self._estado("")
            messagebox.showerror("No se pudo iniciar sesion", str(error))
            return
        self.sesion = sesion
        self.lbl_sesion.config(text=f"Sesion: {sesion.nombre}")
        self._estado("sesion iniciada")
        self._cargar_chats()

    # ── Chats ─────────────────────────────────────────────────────────────
    def _cargar_chats(self) -> None:
        if not self.sesion:
            messagebox.showinfo("Falta iniciar sesion", "Primero inicia sesion con Microsoft.")
            return
        self._estado("cargando chats…")
        self._en_hilo(
            lambda: graph.listar_chats_individuales(self.sesion.token, self.sesion.correo),
            self._chats_listos,
        )

    def _chats_listos(self, chats, error) -> None:
        if error:
            self._estado("")
            # No se deja la lista vacia en silencio: eso se leeria como "no tenes chats".
            messagebox.showerror("No se pudieron cargar los chats", str(error))
            return
        self.chats = chats
        self.lista.delete(0, tk.END)
        for c in chats:
            marca = "→ " if c.lo_ultimo_es_mio else "  "
            self.lista.insert(tk.END, f"{marca}{c.con}")
        self._estado(f"{len(chats)} chat(s) individuales")

    def _al_elegir_chat(self, _evento) -> None:
        sel = self.lista.curselection()
        if not sel or not self.sesion:
            return
        self.chat_actual = self.chats[sel[0]]
        self._estado("cargando conversacion…")
        self._en_hilo(
            lambda: graph.leer_conversacion(
                self.sesion.token, self.chat_actual.id, self.sesion.correo,
                self.ajustes.mensajes_de_contexto,
            ),
            self._conversacion_lista,
        )

    def _conversacion_lista(self, mensajes, error) -> None:
        if error:
            self._estado("")
            messagebox.showerror("No se pudo leer la conversacion", str(error))
            return
        self.conversacion = mensajes
        self.txt_conv.config(state=tk.NORMAL)
        self.txt_conv.delete("1.0", tk.END)
        for m in mensajes:
            quien = "Yo" if m.es_mio else m.de
            self.txt_conv.insert(tk.END, f"{quien}: {m.texto}\n\n")
        self.txt_conv.config(state=tk.DISABLED)
        self.txt_conv.see(tk.END)
        self._estado(f"{len(mensajes)} mensaje(s)")

    # ── Borrador ──────────────────────────────────────────────────────────
    def _ver_envio(self) -> None:
        """Muestra EXACTAMENTE lo que se le mandaria a Groq. Misma funcion que el envio real."""
        if not self.conversacion:
            messagebox.showinfo("Sin conversacion", "Elegi un chat primero.")
            return
        texto = groq.texto_que_se_enviara(self.conversacion, self.ent_indicacion.get())
        v = tk.Toplevel(self)
        v.title("Esto es lo que se enviaria a Groq")
        v.geometry("640x460")
        ttk.Label(
            v,
            text="Este texto sale de la misma funcion que usa el envio real, "
                 "asi que es literalmente lo que se manda. Nada mas sale de tu equipo.",
            wraplength=600, foreground="#666", padding=10,
        ).pack(fill=tk.X)
        c = scrolledtext.ScrolledText(v, wrap=tk.WORD)
        c.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        c.insert("1.0", texto)
        c.config(state=tk.DISABLED)

    def _generar(self) -> None:
        if not self.conversacion:
            messagebox.showinfo("Sin conversacion", "Elegi un chat primero.")
            return
        self.btn_generar.config(state=tk.DISABLED)
        self._estado("redactando…")
        self._en_hilo(
            lambda: groq.redactar_borrador(
                self.ajustes.groq_api_key,
                self.conversacion,
                self.ent_indicacion.get(),
                self.ajustes.modelo,
            ),
            self._borrador_listo,
        )

    def _borrador_listo(self, borrador, error) -> None:
        self.btn_generar.config(state=tk.NORMAL)
        if error:
            self._estado("")
            messagebox.showerror("No se pudo redactar", str(error))
            return
        self.txt_borrador.delete("1.0", tk.END)
        self.txt_borrador.insert("1.0", borrador.texto)
        self._estado(f"borrador listo ({borrador.modelo}) — revisalo antes de enviar")

    # ── Envio ─────────────────────────────────────────────────────────────
    def _enviar(self) -> None:
        texto = self.txt_borrador.get("1.0", tk.END).strip()
        if not self.chat_actual:
            messagebox.showinfo("Sin chat", "Elegi un chat primero.")
            return
        if not texto:
            messagebox.showinfo("Borrador vacio", "No hay nada que enviar.")
            return
        # Un [FALTA: ...] significa que el modelo no tenia el dato. Enviarlo asi seria
        # mandar un mensaje con un hueco. Se bloquea a proposito.
        if "[FALTA:" in texto:
            messagebox.showwarning(
                "El borrador tiene huecos",
                "El borrador contiene marcas [FALTA: ...] porque faltaba informacion en la "
                "conversacion. Completalas antes de enviar.",
            )
            return
        # Confirmacion explicita con el destinatario a la vista: el ultimo punto donde una
        # persona puede notar que iba a mandarle esto a quien no era.
        if not messagebox.askyesno(
            "Confirmar envio",
            f"Enviar a {self.chat_actual.con}?\n\n{texto[:300]}"
            + ("…" if len(texto) > 300 else ""),
        ):
            return

        self.btn_enviar.config(state=tk.DISABLED)
        self._estado("enviando…")
        self._en_hilo(
            lambda: graph.enviar_mensaje(self.sesion.token, self.chat_actual.id, texto),
            self._envio_terminado,
        )

    def _envio_terminado(self, _r, error) -> None:
        self.btn_enviar.config(state=tk.NORMAL)
        if error:
            self._estado("")
            messagebox.showerror("No se pudo enviar", str(error))
            return
        self.txt_borrador.delete("1.0", tk.END)
        self._estado("enviado")
        self._al_elegir_chat(None)  # refresca la conversacion
