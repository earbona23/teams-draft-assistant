"""Punto de entrada.

Si falta configuracion, abre el asistente ANTES de la ventana principal. Arrancar la app
sin configurar produciria errores en cada accion, y la persona no sabria que lo que falta
es un paso de configuracion.
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox

from app import config as cfg


def main() -> int:
    raiz = tk.Tk()
    raiz.withdraw()  # se oculta: solo sirve para poder mostrar dialogos antes de la ventana

    ajustes = cfg.cargar(avisar=lambda m: messagebox.showwarning("Aviso", m))

    if not ajustes.configurado:
        from app.ui.asistente import Asistente

        asis = Asistente(raiz, ajustes)
        raiz.wait_window(asis)
        if not asis.resultado:
            # Cancelo. Se sale sin drama y sin dejar la app a medio configurar.
            return 0
        ajustes = asis.resultado

    raiz.destroy()

    from app.ui.ventana import Ventana

    Ventana(ajustes).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
