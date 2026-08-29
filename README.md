# Asistente de borradores para Microsoft Teams

Lee tus chats **1:1** de Teams, redacta una respuesta con Groq, y **vos la enviás**.

No responde solo. No se hace pasar por vos. No toca chats de grupo.

---

## Qué hace y qué no

| | |
|---|---|
| ✅ Lee tus chats individuales | ❌ No lee chats de grupo ni canales |
| ✅ Redacta un borrador con el contexto | ❌ No envía nada por su cuenta |
| ✅ Te muestra qué se manda a Groq **antes** | ❌ No manda conversaciones en segundo plano |
| ✅ Vos revisás, editás y enviás | ❌ No se hace pasar por vos ante nadie |

### Por qué no responde automáticamente

Fue una decisión, no una limitación técnica.

Un asistente que responde solo con tu nombre significa que tus compañeros creen que hablan con
vos y hablan con un modelo. Si el modelo se equivoca en algo importante, **el error queda escrito
con tu nombre**. Además, automatizar una cuenta de usuario para que hable como humano suele
violar el uso aceptable de Microsoft 365 — y eso es un problema tuyo, personal.

En la práctica el ahorro de tiempo es casi el mismo: lo lento es **pensar** la respuesta, no
apretar enviar.

---

## Cómo se protege tu privacidad, y cómo lo comprobás

Solo se envía a Groq **el chat que abriste**, y solo los últimos 15 mensajes. No hay recorrido
automático de conversaciones.

Pero eso es una afirmación, y las afirmaciones se comprueban. Por eso hay un botón:

> **"Ver qué se envía a Groq"** — muestra el texto exacto que va a salir.

Ese texto sale de **la misma función** que arma el envío real (`texto_que_se_enviara`), así que
no pueden divergir. Y hay un test que lo verifica: si alguien cambiara una y no la otra, la
suite falla.

Es la diferencia entre *"confiá en el README"* y *"mirá vos mismo"*.

---

## Instalación

```bash
git clone <este-repo>
cd teams-draft-assistant
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python -m app.main
```

La primera vez se abre el **asistente de configuración**, que te guía por los dos pasos:
registrar la aplicación en Entra ID y pegar la clave de Groq. Ver
[docs/setup.md](docs/setup.md) si preferís leerlo antes.

**Tres dependencias.** La interfaz usa `tkinter`, que viene con Python.

---

## Permisos que pide, y por qué esos

`Chat.Read` · `ChatMessage.Send` · `User.Read` — **delegados**.

Delegados significa que la aplicación actúa **con tu sesión** y solo puede ver lo que vos podés
ver. La alternativa —permisos de aplicación— le daría acceso a los chats de **toda la
organización**, requeriría aprobación de un administrador, y convertiría el token de una
herramienta personal en una llave del tenant entero.

Para una herramienta personal, pedir permisos de aplicación sería desproporcionado y peligroso.

---

## Cómo se guardan tus credenciales

| Dato | Dónde | Cómo |
|---|---|---|
| Token de Microsoft | `~/.teams-draft-assistant/token.bin` | Cifrado: DPAPI en Windows, Keychain en macOS, libsecret en Linux |
| Clave de Groq | `~/.teams-draft-assistant/groq.bin` | Igual, cifrada |
| ID de aplicación, tenant | `config.json` | En claro — **no son secretos**: el client ID de un cliente público es información pública por diseño |

**Si tu sistema no ofrece almacenamiento cifrado, la aplicación te avisa y te pide la clave en
cada arranque.** Nunca la escribe en texto plano sin decirlo. Escribir un secreto en claro
"porque es una herramienta personal" es exactamente cómo se filtran las claves: alguien sube la
carpeta, hace un respaldo, o comparte la máquina.

---

## Las cuatro decisiones que definen esta herramienta

### 1. Los chats de grupo se filtran dos veces

El código comprueba **el tipo declarado por Graph** y **la forma real del chat** (un 1:1 tiene
exactamente una contraparte). Dos filtros para lo mismo, a propósito: si Graph cambiara el valor
de `chatType` o devolviera algo inesperado, el segundo sigue de pie.

Hay un test por cada filtro **por separado**, y cada uno se verificó eliminando el guard para
confirmar que un test muere. El primer intento **no** los distinguía —los dos casos de prueba
tenían tres miembros, así que el segundo filtro los atrapaba igual— y la prueba de mutación lo
destapó.

### 2. El prompt prohíbe inventar datos

Si para responder falta un dato que no está en la conversación —una fecha, un monto, un
estado—, el modelo debe dejarlo marcado como `[FALTA: ...]` en vez de rellenarlo.

Y **el envío se bloquea si el borrador todavía tiene esas marcas**. Un borrador con una fecha
inventada se envía con tu nombre.

### 3. Generar y Enviar están separados

Nunca se encadenan. Generar no envía; enviar no genera. Y antes de enviar hay una confirmación
**con el destinatario a la vista** — el último punto donde podés notar que se lo ibas a mandar
a quien no era.

### 4. Todo falla cerrado

Si una llamada a Graph falla, se lanza una excepción. **Nunca se devuelve una lista vacía ante
un error**, porque "no tenés chats" y "no pude leerlos" se verían igual — y esa confusión es
justo la que hace que un problema pase inadvertido.

---

## Tests

```bash
python -m pytest        # 24 tests
```

Casi todos son negativos: comprueban que la herramienta **rechaza** lo que tiene que rechazar.
Un test que solo verifica el camino feliz pasaría igual con los guards desconectados.

Cada guard se verificó **eliminándolo** y confirmando que un test muere. Nueve mutantes, nueve
muertos — incluidos los dos filtros de chat grupal, el límite de mensajes que se mandan a Groq,
y la prohibición de inventar datos.

> Durante esa verificación, dos mutantes parecían sobrevivir. No sobrevivían: **la mutación no
> se estaba aplicando** porque buscaba comillas simples donde el código tenía dobles. Una
> mutación que no se aplica se ve idéntica a un mutante que sobrevive, así que el arnés ahora
> comprueba que el archivo haya cambiado antes de dar un resultado.

---

## Estado

**Verificado:** los módulos compilan · la ventana y el asistente se construyen y renderizan ·
24 tests con 9 mutantes muertos · la clave de Groq se prueba contra Groq de verdad.

**No verificado:** el flujo completo contra un tenant real de Teams. Requiere el registro en
Entra ID y una cuenta con Teams. Está escrito acá porque afirmar que algo funciona sin haberlo
ejecutado es la clase de promesa que esta herramienta se propone no hacer — la misma razón por
la que el borrador dice `[FALTA: ...]` en vez de inventar.

## Licencia

MIT. Ver [LICENSE](LICENSE).
