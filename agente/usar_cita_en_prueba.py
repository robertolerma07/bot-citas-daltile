r"""
Fase 3 — Carga en el agente los datos de la cita de un escenario, para probarlo en el navegador.

Toma el folio del escenario de pruebas\esperados.csv y corre subir_agente.py con ese folio
(sube también el prompt y la configuración actuales y comprueba cómo quedó). No gasta créditos.

Uso:
    .venv\Scripts\python agente\usar_cita_en_prueba.py --escenario 3
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from lib.seguridad import detener  # noqa: E402


def escenario(numero):
    """Regresa la fila de pruebas/esperados.csv del escenario indicado."""
    with (RAIZ / "pruebas" / "esperados.csv").open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if fila["escenario"] == str(numero):
                return fila
    detener(f"No existe el escenario {numero} en pruebas/esperados.csv")


def main():
    parser = argparse.ArgumentParser(description="Carga la cita de un escenario en el agente.")
    parser.add_argument("--escenario", type=int, required=True, help="número de escenario (1 a 8)")
    args = parser.parse_args()

    e = escenario(args.escenario)
    print(f"Escenario {e['escenario']}: {e['nombre']} — {e['tipo_contacto']}, folio {e['folio']}\n", flush=True)
    resultado = subprocess.run([sys.executable, str(RAIZ / "agente" / "subir_agente.py"), "--folio", e["folio"]])
    if resultado.returncode == 0:
        print("\nListo: abre el agente en ElevenLabs y llama con el botón del teléfono.")
        print("Guion del escenario: pruebas/escenarios.md")
    sys.exit(resultado.returncode)


if __name__ == "__main__":
    main()
