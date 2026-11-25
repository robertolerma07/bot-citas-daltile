# Guía: servidor de prueba del seguimiento de domingo

Para Roberto. Sigue los pasos en orden; cada uno dice **qué haces, para qué sirve y cuánto cuesta**. Los comandos están
en bloques de código: se copian y se pegan tal cual. Nunca pegues contraseñas ni keys en un chat.

**Regla de oro:** el servidor `srm-piloto` es de otro sistema (el SRM). **No lo toques.** Aquí se crea una instancia
**nueva**, con otro nombre.

## Qué vas a tener al final
- Un servidor chico en AWS Lightsail que corre dos cosas: la **página web** donde subes y apruebas la lista de viajes del
  domingo, y el **latido**, un reloj que cada 5 minutos revisa si toca llamar, reintentar o mandar correos.
- La página con candadito (HTTPS), en una dirección como `https://3-140-10-20.sslip.io`.

## Parte A. Cosas que haces fuera del servidor

### A1. Twilio: subir de cuenta de prueba a cuenta pagada
- **Para qué:** la cuenta de prueba solo llama a números verificados y pone un aviso al inicio de cada llamada.
- **Cómo:** en https://console.twilio.com, **Upgrade**, agrega tarjeta y un saldo inicial pequeño (por ejemplo USD 20).
- **Importante:** deja **apagada** la recarga automática (*Auto-recharge OFF*), para que nunca cobre de más sin que lo
  decidas.
- **Costo:** el saldo que cargues; se gasta solo con llamadas y con la renta del número.

### A2. Twilio: comprar un número de EE. UU. con voz
- **Para qué:** es el número desde el que llama Sofía mientras llega el número mexicano.
- **Cómo:** *Phone Numbers → Manage → Buy a number*, país Estados Unidos, marca la capacidad **Voice**.
- **Costo:** unos USD 1.15 al mes más el costo por minuto de las llamadas a México.
- Anota el número (formato `+1XXXXXXXXXX`); va en el `.env` como `TWILIO_NUMERO`.

### A3. Twilio: permitir llamadas a México
- *Voice → Settings → Geo permissions*, confirma que **Mexico** está palomeado. Sin eso, las llamadas fallan.
- **Costo:** ninguno.

### A4. Registrar el número en ElevenLabs
- Se hace **desde tu PC** (donde ya tienes el `.env`), con `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` y `TWILIO_NUMERO`
  ya llenos:
  ```
  .venv\Scripts\python herramientas\registrar_numero.py
  ```
- Esto llena `ELEVENLABS_PHONE_NUMBER_ID` en tu `.env`. Ese valor lo copias al `.env` del servidor (paso C3).
- **Costo:** ninguno.

### A5. Un Gmail dedicado al bot
- **Para qué:** de ahí salen los correos de aprobación, de monitoreo y de control. No uses tu correo personal.
- **Cómo:**
  1. Crea una cuenta de Gmail nueva solo para el bot.
  2. Entra a *Cuenta de Google → Seguridad* y activa la **verificación en dos pasos**.
  3. En la misma sección busca **Contraseñas de aplicaciones**, crea una llamada `bot domingo` y copia la clave de 16
     letras. Esa clave va en el `.env` como `SMTP_PASSWORD` (no es la contraseña normal de la cuenta).
- **Costo:** ninguno.

### A6. Plan de ElevenLabs con créditos suficientes
- El plan Free trae unos 7,000 créditos restantes, que son **unos 7 minutos de llamadas**: no alcanza ni para el ensayo.
- Sube a un plan con más créditos (en *Subscription* ves el precio y los créditos de cada plan). Calcula unos 935
  créditos por minuto de llamada, según lo medido.

### A7. Trámite del número mexicano (empieza ya, tarda)
- **Para qué:** un número mexicano contesta mejor que uno de EE. UU. y evita que los operadores no contesten.
- **Cómo:** en Twilio, *Phone Numbers → Regulatory Compliance → Bundles*, crea un *Bundle* para México con los
  documentos de la empresa que pida. Twilio lo revisa en **días o semanas**; no bloquea el ensayo.
- **Costo:** el número mexicano tiene renta mensual; Twilio la muestra antes de comprar.

## Parte B. Crear el servidor en AWS Lightsail

### B1. Crear la instancia nueva
1. Entra a Lightsail con tu sesión de AWS: https://lightsail.aws.amazon.com
2. **Create instance**. Región: la misma de `srm-piloto` o la más cercana a México.
3. Plataforma **Linux/Unix**, blueprint **OS Only → Ubuntu 24.04 LTS**.
4. Plan: el más barato **que tenga IPv4 pública (dual-stack, no "solo IPv6")** y **al menos 1 GB de RAM**. Con solo IPv6 no funcionan GitHub por SSH, la IP fija ni sslip.io. **Cuesta unos USD 5 a 7 al mes; confirma el precio vigente en la pantalla.** Si de todos modos eliges 512 MB, crea memoria extra con estos comandos en la terminal del servidor, una sola vez (sin ella, la instalación de las dependencias puede fallar por falta de memoria):
   ```
   sudo fallocate -l 1G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
   ```
5. Nombre de la instancia: `bot-domingo`. **No uses ni toques `srm-piloto`.**
6. **Create instance** y espera a que diga *Running*.

### B2. IP fija y puertos
1. En la instancia nueva: pestaña **Networking → Attach static IP → Create and attach**. Sin IP fija, la dirección
   cambiaría al reiniciar y la página dejaría de abrir. La IP estática es gratis mientras esté conectada.
2. En **IPv4 Firewall** deja **SSH (22)** y agrega **HTTP (80)** y **HTTPS (443)**. Nada más.
3. Anota la IP, por ejemplo `3.140.10.20`. La dirección de la página será esa IP con **guiones**:
   `https://3-140-10-20.sslip.io` (el servicio sslip.io convierte esa dirección en tu IP, gratis, y permite el
   candadito sin comprar dominio).

### B3. Entrar al servidor
La red de la oficina bloquea SSH normal. Entra por el navegador: en la instancia, botón **Connect using SSH**. Se abre una
terminal en otra pestaña. Ahí pegas los comandos de abajo (clic derecho, pegar).

## Parte C. Instalar el bot

### C1. Crear el usuario `sofia` y la llave de solo lectura de GitHub
El bot corre con un usuario propio llamado `sofia` (la página y el latido deben ser del mismo usuario).
```
sudo adduser --disabled-password --gecos "" sofia
sudo -u sofia mkdir -p /home/sofia/.ssh
sudo -u sofia chmod 700 /home/sofia/.ssh
sudo -u sofia ssh-keygen -t ed25519 -N "" -C "bot-domingo" -f /home/sofia/.ssh/id_ed25519
sudo cat /home/sofia/.ssh/id_ed25519.pub
```
El último comando muestra una línea que empieza con `ssh-ed25519`. Cópiala completa.

En GitHub: repositorio `robertolerma07/bot-citas-daltile` → **Settings → Deploy keys → Add deploy key**. Ponle un título
(`bot-domingo`), pega la línea y **deja sin palomear "Allow write access"** (solo lectura: el servidor puede bajar el
código pero nunca cambiarlo).

### C2. Bajar el código y correr el instalador
```
sudo -u sofia bash -c 'ssh-keyscan -t ed25519 github.com >> /home/sofia/.ssh/known_hosts'
sudo -u sofia git clone --branch domingo-mvp git@github.com:robertolerma07/bot-citas-daltile.git /home/sofia/bot-citas-daltile
sudo bash /home/sofia/bot-citas-daltile/despliegue/instalar.sh
```
- `domingo-mvp` es la rama de trabajo; cuando se junte con `master`, usa `sudo RAMA=master bash /home/sofia/bot-citas-daltile/despliegue/instalar.sh`.
- El instalador pone Python, las dependencias, Caddy (el que da el candadito), el servicio de la página y el latido cada
  5 minutos. La hora del servidor no importa: el bot usa siempre la hora de Ciudad de México.
- La **primera vez se detiene** con un mensaje que dice qué falta (`.env` y la lista de celulares). Es normal: sigue con
  C3 y C4 y luego vuelve a correr el mismo comando. Se puede correr las veces que quieras.

### C3. Llenar el `.env` a mano
```
sudo -u sofia cp /home/sofia/bot-citas-daltile/.env.example /home/sofia/bot-citas-daltile/.env
sudo -u sofia chmod 600 /home/sofia/bot-citas-daltile/.env
sudo -u sofia nano /home/sofia/bot-citas-daltile/.env
```
En `nano` escribe cada valor después del `=`, sin espacios ni comillas. Guarda con `Ctrl+O`, Enter, y sal con `Ctrl+X`.

| Llave | Qué poner |
|---|---|
| `ELEVENLABS_API_KEY` | la misma de tu PC |
| `ELEVENLABS_AGENT_ID` | el agente de avisos, de tu `.env` |
| `ELEVENLABS_AGENT_ID_SEGUIMIENTO` | el agente "Sofía - seguimiento", de tu `.env` |
| `ELEVENLABS_PHONE_NUMBER_ID` | el que llenó `registrar_numero.py` (A4) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | de la consola de Twilio |
| `TWILIO_NUMERO` | el número de EE. UU. (A2) |
| `SMTP_HOST` y `SMTP_PUERTO` | `smtp.gmail.com` y `587` |
| `SMTP_USUARIO` | el Gmail del bot (A5) |
| `SMTP_PASSWORD` | la contraseña de aplicación de 16 letras (A5) |
| `CORREO_CONTROL` | tu correo |
| `PAGINA_PASSWORD` | la contraseña con la que el equipo entra a la página |
| `PAGINA_SECRETO` | un texto largo al azar; genéralo con el comando de abajo |

```
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Copia el resultado como `PAGINA_SECRETO`. Si algún día cambias `PAGINA_PASSWORD`, reinicia la página:
`sudo systemctl restart bot-domingo-pagina` (el `.env` se lee una sola vez al arrancar).

### C4. Lista de celulares permitidos
Mientras el bot esté en modo ensayo (`"ensayo": true` en `config/domingo.json`), solo llama a los celulares de esta lista:
```
sudo -u sofia nano /home/sofia/bot-citas-daltile/config/numeros_permitidos.txt
sudo -u sofia chmod 600 /home/sofia/bot-citas-daltile/config/numeros_permitidos.txt
```
Un celular por línea, con `+52` y 10 dígitos (por ejemplo `+525512345678`). Pon los celulares del equipo que harán el
ensayo.

### C5. Terminar la instalación y revisar
```
sudo bash /home/sofia/bot-citas-daltile/despliegue/instalar.sh
```
Al final dice `LISTO. La pagina queda en: https://...sslip.io`. Abre esa dirección en tu navegador: debe pedir la
contraseña. (Si no abre al instante, espera uno o dos minutos: Caddy está sacando el candadito.)

Revisa las conexiones sin llamar a nadie:
```
sudo -u sofia /home/sofia/bot-citas-daltile/.venv/bin/python /home/sofia/bot-citas-daltile/verificar_conexion.py
sudo systemctl status bot-domingo-pagina --no-pager
sudo -u sofia crontab -l
```
`verificar_conexion.py` no hace llamadas ni gasta; debe decir que las keys de ElevenLabs y Twilio funcionan y si México
está habilitado.

## Parte D. Actualizar el código más adelante
Cuando haya cambios nuevos en GitHub, en la terminal del servidor:
```
sudo bash /home/sofia/bot-citas-daltile/despliegue/instalar.sh
```
Baja la rama, actualiza dependencias y reinicia la página. Tu `.env` y tus datos no se tocan.

## Parte E. Si algo falla
- **La página no abre:** `sudo systemctl status bot-domingo-pagina --no-pager` y
  `sudo journalctl -u bot-domingo-pagina -n 50`. Si dice que faltan `PAGINA_PASSWORD` o `PAGINA_SECRETO`, revisa el `.env`.
- **Sin candadito:** `sudo journalctl -u caddy -n 50`. Revisa que los puertos 80 y 443 estén abiertos en Lightsail.
- **El latido no hace nada:** es normal fuera de domingo. Revisa `resultados/domingo/latido.log` y
  `resultados/domingo/cron.log`.
- **El instalador dice que falta algo:** lee el mensaje; dice el archivo exacto.
- **Quieres dejar de gastar:** detener (*Stop*) la instancia **no** detiene el cobro; Lightsail sigue cobrando una
  instancia detenida. El cobro solo termina cuando **borras** la instancia (si quieres conservarla, antes crea una
  *snapshot*, que también tiene un costo pequeño) y **liberas la IP estática**: una IP estática que no está conectada a
  una instancia también se cobra. Nunca borres `srm-piloto`.
