#!/usr/bin/env bash
# Instala o actualiza el bot de domingo en un servidor Ubuntu 24.04.
# Uso:  sudo bash instalar.sh            (se puede correr varias veces sin problema)
# Rama distinta:  sudo RAMA=master bash instalar.sh
set -euo pipefail

RAMA="${RAMA:-domingo-mvp}"
REPO_URL="git@github.com:robertolerma07/bot-citas-daltile.git"
USUARIO="sofia"
CASA="/home/${USUARIO}"
CARPETA="${CASA}/bot-citas-daltile"
SERVICIO="bot-domingo-pagina"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: corre este script con sudo:  sudo bash instalar.sh" >&2
  exit 1
fi

# Evita correr desde una carpeta que el usuario sofia no puede leer
cd /

echo "== 1/8 Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl gpg debian-keyring debian-archive-keyring apt-transport-https

echo "== 2/8 Usuario ${USUARIO}"
if ! id "${USUARIO}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${USUARIO}"
fi

echo "== 3/8 Codigo (rama ${RAMA})"
LLAVE="${CASA}/.ssh/id_ed25519"
if [ ! -f "${LLAVE}" ]; then
  sudo -u "${USUARIO}" mkdir -p "${CASA}/.ssh"
  chmod 700 "${CASA}/.ssh"
  sudo -u "${USUARIO}" ssh-keygen -t ed25519 -N "" -C "srm-bot-domingo" -f "${LLAVE}"
  echo
  echo "Se creo la llave de despliegue. Copia esta linea completa en GitHub:"
  echo "(repositorio -> Settings -> Deploy keys -> Add deploy key, SIN marcar 'Allow write access')"
  echo
  cat "${LLAVE}.pub"
  echo
  echo "Cuando la hayas agregado en GitHub, vuelve a correr:  sudo bash instalar.sh"
  exit 0
fi
sudo -u "${USUARIO}" bash -c "ssh-keyscan -t ed25519 github.com >> '${CASA}/.ssh/known_hosts' 2>/dev/null; sort -u -o '${CASA}/.ssh/known_hosts' '${CASA}/.ssh/known_hosts'"
if [ ! -d "${CARPETA}/.git" ]; then
  sudo -u "${USUARIO}" git clone --branch "${RAMA}" "${REPO_URL}" "${CARPETA}" || {
    echo "ERROR: no se pudo clonar. Revisa que la llave de despliegue este agregada en GitHub." >&2
    exit 1
  }
else
  sudo -u "${USUARIO}" git -C "${CARPETA}" fetch origin
  sudo -u "${USUARIO}" git -C "${CARPETA}" checkout "${RAMA}"
  sudo -u "${USUARIO}" git -C "${CARPETA}" pull --ff-only origin "${RAMA}"
fi

echo "== 4/8 Entorno de Python y dependencias"
if [ ! -x "${CARPETA}/.venv/bin/python" ]; then
  sudo -u "${USUARIO}" python3 -m venv "${CARPETA}/.venv"
fi
sudo -u "${USUARIO}" "${CARPETA}/.venv/bin/python" -m pip install --quiet --upgrade pip
sudo -u "${USUARIO}" "${CARPETA}/.venv/bin/python" -m pip install --quiet -r "${CARPETA}/requirements.txt"
sudo -u "${USUARIO}" mkdir -p "${CARPETA}/resultados/domingo"

echo "== 5/8 Caddy (HTTPS)"
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo "== 6/8 Archivos que faltan por crear a mano"
FALTA=0
if [ ! -f "${CARPETA}/.env" ]; then
  echo "FALTA: ${CARPETA}/.env  (copialo de .env.example y llenalo; ver la guia, paso del .env)"
  FALTA=1
fi
if [ ! -f "${CARPETA}/config/numeros_permitidos.txt" ]; then
  echo "FALTA: ${CARPETA}/config/numeros_permitidos.txt  (un celular +52XXXXXXXXXX por linea)"
  FALTA=1
fi
if [ "${FALTA}" -ne 0 ]; then
  echo
  echo "Todavia NO se activo la pagina. Crea lo que falta, ponle permisos con:"
  echo "  sudo chown ${USUARIO}:${USUARIO} <archivo> && sudo chmod 600 <archivo>"
  echo "y vuelve a correr:  sudo bash instalar.sh"
  exit 1
fi
chown "${USUARIO}:${USUARIO}" "${CARPETA}/.env" "${CARPETA}/config/numeros_permitidos.txt"
chmod 600 "${CARPETA}/.env" "${CARPETA}/config/numeros_permitidos.txt"

echo "== 7/8 Servicio de la pagina y Caddy"
cp "${CARPETA}/despliegue/${SERVICIO}.service" "/etc/systemd/system/${SERVICIO}.service"
systemctl daemon-reload
systemctl enable "${SERVICIO}"
systemctl restart "${SERVICIO}"

IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
DOMINIO="$(echo "${IP}" | tr '.' '-').sslip.io"
sed "s/DOMINIO_AQUI/${DOMINIO}/" "${CARPETA}/despliegue/Caddyfile" > /etc/caddy/Caddyfile
systemctl enable caddy
systemctl restart caddy

echo "== 8/8 Latido cada 5 minutos"
sudo -u "${USUARIO}" crontab "${CARPETA}/despliegue/crontab.txt"

echo
echo "LISTO. La pagina queda en: https://${DOMINIO}"
echo "Revisa el estado con:  systemctl status ${SERVICIO} --no-pager"
