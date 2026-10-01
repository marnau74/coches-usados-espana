import hashlib
import json

import duckdb
import pytest

from coches_usados import release


@pytest.fixture(scope="module")
def paquete(warehouse_sintetico, tmp_path_factory):
    salida = tmp_path_factory.mktemp("release")
    contrato = release.exportar(warehouse_sintetico, salida)
    return salida, contrato


def test_la_release_trae_un_parquet_por_tabla_de_gold_el_duckdb_el_contrato_y_las_sumas(paquete):
    salida, contrato = paquete
    nombres = {f.name for f in salida.iterdir()}
    assert nombres == {
        "coches_usados.duckdb", "contrato.json", "SHA256SUMS",
        *(f"{t}.parquet" for t in contrato["tablas"]),
    }  # fmt: skip
    assert set(contrato["tablas"]) == {
        "dim_combustible", "dim_fecha", "dim_provincia", "fct_modelos_mensual",
        "fct_precios_indice_mensual", "fct_titularidad_anual", "fct_tramites_mensual",
    }  # fmt: skip


def test_el_contrato_describe_el_periodo_las_fuentes_y_el_esquema_de_cada_tabla(paquete):
    _, contrato = paquete
    assert contrato["version_contrato"] == release.VERSION_CONTRATO
    assert contrato["periodo"] == {"desde": "2024-01", "hasta": "2024-12"}
    assert contrato["provisional_desde"] == "2024-11"
    assert any("DGT" in f for f in contrato["fuentes"])
    columnas = {c["nombre"]: c["tipo"] for c in contrato["tablas"]["fct_tramites_mensual"]["columnas"]}
    assert columnas["tramites"] == "INTEGER"
    assert columnas["tramo_antiguedad"] == "VARCHAR"


def test_el_contrato_cuenta_las_filas_reales_de_cada_parquet(paquete):
    salida, contrato = paquete
    for tabla, datos in contrato["tablas"].items():
        (filas,) = duckdb.sql(
            f"SELECT count(*) FROM read_parquet('{(salida / f'{tabla}.parquet').as_posix()}')"
        ).fetchone()
        assert filas == datos["filas"] > 0


def test_las_sumas_de_verificacion_coinciden_con_los_ficheros(paquete):
    salida, _ = paquete
    lineas = (salida / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    assert len(lineas) == len(list(salida.iterdir())) - 1
    for linea in lineas:
        suma, nombre = linea.split("  ")
        assert hashlib.sha256((salida / nombre).read_bytes()).hexdigest() == suma
    assert json.loads((salida / "contrato.json").read_text(encoding="utf-8"))["tablas"]


def test_el_duckdb_de_la_release_tiene_el_esquema_gold(paquete):
    salida, _ = paquete
    with duckdb.connect(str(salida / release.NOMBRE_DUCKDB), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM gold.fct_tramites_mensual").fetchone()[0] > 0


def test_exportar_sobre_un_warehouse_sin_gold_falla_y_no_modifica_el_warehouse(tmp_path):
    vacio = tmp_path / "w.duckdb"
    duckdb.connect(str(vacio)).close()
    with pytest.raises(ValueError, match="gold"):
        release.exportar(vacio, tmp_path / "salida")
