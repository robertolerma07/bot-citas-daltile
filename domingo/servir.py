r"""
Sirve la página del domingo con waitress en 127.0.0.1:8080 (Caddy le pone el HTTPS por delante):
    .venv\Scripts\python -m domingo.servir

Necesita PAGINA_PASSWORD y PAGINA_SECRETO en .env; sin ellas no arranca. El bloqueo por intentos
fallidos vive en memoria: reiniciar el servicio lo borra.
"""

import sys

from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

from domingo.almacen import RAIZ_DOMINGO
from domingo.calendario import cargar_calendario
from domingo.pagina import TAMANO_MAXIMO, crear_app
from lib.seguridad import cargar_env

HOST = "127.0.0.1"
PUERTO = 8080
OPCIONALES = ["CORREO_CONTROL", "SMTP_HOST", "SMTP_PUERTO", "SMTP_USUARIO", "SMTP_PASSWORD"]


def main():
    env, faltantes = cargar_env(["PAGINA_PASSWORD", "PAGINA_SECRETO"] + OPCIONALES)
    obligatorias = [n for n in faltantes if n.startswith("PAGINA_")]
    if obligatorias:
        print(f"No se puede arrancar la página: falta {', '.join(obligatorias)} en .env "
              "(la contraseña del equipo y un secreto largo al azar para firmar la sesión).")
        return 1
    try:
        app = crear_app(RAIZ_DOMINGO, env, cargar_calendario())
    except ValueError as e:
        print(f"No se puede arrancar la página: {e}")
        return 1
    # Detrás de Caddy: la IP real del visitante viene en X-Forwarded-For (la agrega Caddy) y el
    # esquema en X-Forwarded-Proto.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    print(f"Página del domingo en http://{HOST}:{PUERTO} (Ctrl+C para detenerla)")
    serve(app, host=HOST, port=PUERTO, threads=4, max_request_body_size=TAMANO_MAXIMO + 1024 * 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
