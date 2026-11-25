"""
Teléfono de Monitoreo dicho como pidió Roberto (2026-11-25): los primeros 2 pares y los últimos
6 dígitos en dos grupos de 3. Por ejemplo, 81 83 004 500.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from lib.formato_voz import telefono_por_grupos  # noqa: E402


@pytest.mark.parametrize("telefono, texto", [
    ("+528183004500", "ochenta y uno... ochenta y tres... cero cero cuatro... quinientos"),
    ("+525500000003", "cincuenta y cinco... cero cero... cero cero cero... cero cero tres"),
    ("+523312345678", "treinta y tres... doce... trescientos cuarenta y cinco... seiscientos setenta y ocho"),
    ("+528112045100", "ochenta y uno... doce... cero cuarenta y cinco... cien"),
    ("+525505123010", "cincuenta y cinco... cero cinco... ciento veintitrés... cero diez"),
])
def test_telefono_por_grupos(telefono, texto):
    assert telefono_por_grupos(telefono) == texto


def test_telefono_por_grupos_digito_por_digito():
    assert telefono_por_grupos("+528183004500", digito_por_digito=True) == \
        "ocho, uno... ocho, tres... cero, cero, cuatro... cinco, cero, cero"


def test_telefono_por_grupos_rechaza_numero_incompleto():
    with pytest.raises(ValueError):
        telefono_por_grupos("+52818300450")


def test_monitoreo_usa_grupos_2_2_3_3():
    from domingo.viajes import variables_de_voz_viaje
    viaje = {"operador": "X", "linea": "L", "cliente": "C", "destino": "D", "fecha_cita": "2026-11-30",
             "tipo_cita": "Hora", "limite": "08:00", "telefono_monitoreo": "+528183004500"}
    v = variables_de_voz_viaje(viaje)
    assert v["tel_monitoreo_texto"] == "ochenta y uno... ochenta y tres... cero cero cuatro... quinientos"
    assert v["tel_monitoreo_digitos"] == "ocho, uno... ocho, tres... cero, cero, cuatro... cinco, cero, cero"
