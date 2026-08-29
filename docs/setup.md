# Guía de configuración

Dos pasos. El primero es el que hace fracasar a la mayoría, así que va con las trampas señaladas.

---

## 1 · Registrar la aplicación en Entra ID

Sin esto la aplicación no puede hablar con Teams. Es gratis y toma unos minutos.

1. Entrá a **[Microsoft Entra ID](https://entra.microsoft.com)** con tu cuenta de trabajo.

2. **Registros de aplicaciones → Nuevo registro**
   - **Nombre:** el que quieras, por ejemplo *Asistente de borradores*.
   - **Tipos de cuenta compatibles:** *Solo cuentas de este directorio organizativo*.
   - **URI de redirección:** **dejala vacía**. No hace falta ninguna.
   - **Registrar**.

3. Copiá el **Id. de aplicación (cliente)**. Es lo que vas a pegar en el asistente.

4. **Autenticación → Configuración avanzada**
   - **Permitir flujos de cliente público → Sí** → *Guardar*.

   > ⚠️ **Esta es la trampa número uno.** Sin este paso el inicio de sesión falla con un error
   > que no menciona en ningún momento esta casilla. Si algo va a fallar, va a fallar acá.

5. **Permisos de API → Agregar un permiso → Microsoft Graph → Permisos delegados**
   - Marcá: `Chat.Read`, `ChatMessage.Send`, `User.Read`
   - **Agregar permisos**.

   > ⚠️ **Trampa número dos: tienen que ser DELEGADOS, no de aplicación.**
   > Delegados = la app ve solo lo que ves vos.
   > De aplicación = la app vería los chats de **toda la organización**, necesita aprobación de
   > un administrador, y convierte el token de tu herramienta personal en una llave del tenant.

No hace falta "Conceder consentimiento del administrador": con permisos delegados, el
consentimiento lo das vos al iniciar sesión por primera vez.

---

## 2 · Clave de Groq

1. Entrá a **[console.groq.com/keys](https://console.groq.com/keys)** y creá una clave.
2. **Copiala en ese momento.** Groq la muestra una sola vez; si cerrás esa pantalla, hay que
   crear otra.
3. Pegala en el asistente y tocá **Probar** — la comprueba contra Groq de verdad, para que si
   está mal te enteres ahí y no en tu primer borrador.

---

## Primer uso

1. `python -m app.main`
2. **Iniciar sesión** → aparece un código.
3. Abrí la dirección que te muestra, escribí el código, autorizá los permisos.
4. Volvé a la ventana: se actualiza sola y carga tus chats individuales.

---

## Si algo falla

| Lo que ves | Qué es |
|---|---|
| *"No se pudo iniciar el flujo de dispositivo"* | Falta el paso 4: **Permitir flujos de cliente público** |
| *"Graph rechazó la petición por permisos"* | Los permisos son de aplicación en vez de delegados, o falta alguno |
| *"La sesión venció"* | Normal cada tantos días. Tocá **Iniciar sesión** de nuevo |
| *"Groq rechazó la clave"* | La clave se copió mal o se revocó. Creá otra |
| No aparece ningún chat | ¿Tenés chats **1:1**? Los de grupo no se muestran, por diseño |

---

## Cómo desinstalar

Borrá la carpeta del repositorio y `~/.teams-draft-assistant` (ahí viven el token cifrado y la
clave). Y si querés, eliminá el registro de la aplicación en Entra ID.
