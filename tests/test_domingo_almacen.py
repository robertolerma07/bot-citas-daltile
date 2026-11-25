"""Pruebas de la aprobación y el estado guardados del domingo (todo bajo tmp_path)."""

import json
import os
import time
from datetime import date, datetime, timedelta

import pytest

from domingo import almacen
from domingo.almacen import CandadoOcupado
from domingo.reglas import estado_inicial
from lib.seguridad import ZONA_CDMX

DOMINGO = date(2026, 11, 29)
AHORA = datetime(2026, 11, 28, 18, 0, tzinfo=ZONA_CDMX)
VIAJES = [
    {"viaje": "V1", "operador": "Ana", "_fila": 2, "limite": "16:00"},
    {"viaje": "V2", "operador": "Beto", "_fila": 3, "limite": "16:00"},
]


def test_carpeta_por_fecha(tmp_path):
    assert almacen.carpeta(DOMINGO, tmp_path) == tmp_path / "2026-11-29"


def test_aprobacion_ida_y_vuelta(tmp_path):
    almacen.guardar_aprobacion(DOMINGO, VIAJES, b"excel1", "Roberto", AHORA, raiz=tmp_path)
    ap = almacen.leer_aprobacion(DOMINGO, raiz=tmp_path)
    assert ap["quien"] == "Roberto"
    assert ap["viajes"] == VIAJES
    assert datetime.fromisoformat(ap["cuando"]) == AHORA
    assert (almacen.carpeta(DOMINGO, tmp_path) / "viajes.xlsx").read_bytes() == b"excel1"


def test_sin_aprobacion_devuelve_none(tmp_path):
    assert almacen.leer_aprobacion(DOMINGO, raiz=tmp_path) is None


def test_nueva_aprobacion_reemplaza(tmp_path):
    almacen.guardar_aprobacion(DOMINGO, VIAJES, b"excel1", "Roberto", AHORA, raiz=tmp_path)
    almacen.guardar_aprobacion(DOMINGO, VIAJES[:1], b"excel2", "Laura", AHORA, raiz=tmp_path)
    ap = almacen.leer_aprobacion(DOMINGO, raiz=tmp_path)
    assert ap["quien"] == "Laura"
    assert ap["viajes"] == VIAJES[:1]
    assert (almacen.carpeta(DOMINGO, tmp_path) / "viajes.xlsx").read_bytes() == b"excel2"


def test_estados_ida_y_vuelta_con_fechas_con_zona(tmp_path):
    est = estado_inicial()
    est["ultimo_intento"] = AHORA
    est["en_curso"] = {"conversacion": "conv_1", "inicio": AHORA}
    est["historial"].append({"fecha": AHORA.isoformat(), "resultado": "sin_respuesta"})
    almacen.guardar_estados(DOMINGO, {"V1": est}, raiz=tmp_path)
    leido = almacen.cargar_estados(DOMINGO, raiz=tmp_path)
    assert leido == {"V1": est}
    assert isinstance(leido["V1"]["ultimo_intento"], datetime)
    assert leido["V1"]["ultimo_intento"].utcoffset() is not None
    assert isinstance(leido["V1"]["en_curso"]["inicio"], datetime)
    assert isinstance(leido["V1"]["historial"][0]["fecha"], str)


def test_cargar_estados_sin_archivo_es_vacio(tmp_path):
    assert almacen.cargar_estados(DOMINGO, raiz=tmp_path) == {}


def test_estados_de_completa_con_estado_inicial(tmp_path):
    almacen.guardar_aprobacion(DOMINGO, VIAJES, b"x", "Roberto", AHORA, raiz=tmp_path)
    guardado = estado_inicial()
    guardado["estado"] = "a_tiempo"
    almacen.guardar_estados(DOMINGO, {"V1": guardado}, raiz=tmp_path)
    estados = almacen.estados_de(DOMINGO, VIAJES, raiz=tmp_path)
    assert estados["V1"]["estado"] == "a_tiempo"
    assert estados["V2"] == estado_inicial()


def test_escritura_atomica(tmp_path):
    almacen.guardar_estados(DOMINGO, {"V1": estado_inicial()}, raiz=tmp_path)
    mal = {"V1": {"raro": object()}}
    with pytest.raises(TypeError):
        almacen.guardar_estados(DOMINGO, mal, raiz=tmp_path)
    assert almacen.cargar_estados(DOMINGO, raiz=tmp_path) == {"V1": estado_inicial()}
    assert [p.name for p in almacen.carpeta(DOMINGO, tmp_path).iterdir()] == ["estados.json"]


def test_detener_y_detenido(tmp_path):
    assert almacen.detenido(DOMINGO, raiz=tmp_path) is None
    almacen.detener(DOMINGO, "Roberto", AHORA, raiz=tmp_path)
    d = almacen.detenido(DOMINGO, raiz=tmp_path)
    assert d["quien"] == "Roberto"
    assert datetime.fromisoformat(d["cuando"]) == AHORA


def test_marcar_hecho_una_vez(tmp_path):
    assert not almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)
    almacen.marcar_hecho(DOMINGO, "correo_1300", AHORA, raiz=tmp_path)
    assert almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)
    assert not almacen.ya_hecho(DOMINGO, "resumen", raiz=tmp_path)
    # marcar otra clave no borra la anterior
    almacen.marcar_hecho(DOMINGO, "resumen", AHORA, raiz=tmp_path)
    assert almacen.ya_hecho(DOMINGO, "correo_1300", raiz=tmp_path)


def test_candado(tmp_path):
    with almacen.candado(raiz=tmp_path):
        with pytest.raises(CandadoOcupado):
            with almacen.candado(raiz=tmp_path):
                pass
    # al salir se libera
    with almacen.candado(raiz=tmp_path):
        pass
    assert list(tmp_path.glob("*.lock")) == []


def test_candado_se_libera_aunque_falle_el_cuerpo(tmp_path):
    with pytest.raises(RuntimeError):
        with almacen.candado(raiz=tmp_path):
            raise RuntimeError("falla")
    with almacen.candado(raiz=tmp_path):
        pass


def test_candado_viejo_se_reemplaza(tmp_path):
    ruta = tmp_path / "latido.lock"
    ruta.write_text("viejo")
    hace_3h = time.time() - 3 * 3600
    os.utime(ruta, (hace_3h, hace_3h))
    with almacen.candado(raiz=tmp_path):
        assert ruta.exists()
    assert not ruta.exists()


def test_candado_reciente_bloquea(tmp_path):
    (tmp_path / "latido.lock").write_text("otro")
    with pytest.raises(CandadoOcupado):
        with almacen.candado(raiz=tmp_path):
            pass
    assert (tmp_path / "latido.lock").exists()


def test_fallas_del_dia_sin_repetir(tmp_path):
    assert almacen.fallas_del_dia(DOMINGO, raiz=tmp_path) == []
    assert almacen.anotar_falla(DOMINGO, "Viaje V1: fuera de la lista blanca", AHORA, raiz=tmp_path)
    assert not almacen.anotar_falla(DOMINGO, "Viaje V1: fuera de la lista blanca", AHORA, raiz=tmp_path)
    assert almacen.anotar_falla(DOMINGO, "Falta CORREO_CONTROL", AHORA, raiz=tmp_path)
    fallas = almacen.fallas_del_dia(DOMINGO, raiz=tmp_path)
    assert [f["texto"] for f in fallas] == ["Viaje V1: fuera de la lista blanca", "Falta CORREO_CONTROL"]
    assert datetime.fromisoformat(fallas[0]["cuando"]) == AHORA
