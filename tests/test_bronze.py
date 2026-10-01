import os
import time
import zipfile
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd
import pytest

from coches_usados import bronze
from coches_usados.ingest.dgt import TIPOS
from coches_usados.ingest.diseno_registro import LONGITUD_LINEA
from tests import sinteticos


def zip_de(ruta: Path, lineas: list[str], codificacion: str = "latin-1", separador: str = "\r\n") -> Path:
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr(f"{ruta.stem}.txt", (separador.join(lineas) + separador).encode(codificacion))
    return ruta


def linea(**campos) -> str:
    return sinteticos._linea(**campos)


def test_las_lineas_se_leen_en_latin_1_sin_perder_las_con_enie(tmp_path):
    ruta = zip_de(tmp_path / "export_mensual_trf_202401.zip", [linea(municipio="A CORUÑA"), linea(municipio="LEÓN")])
    lineas = bronze.lineas_del_zip(ruta)
    assert len(lineas) == 2
    assert all(len(x) == LONGITUD_LINEA for x in lineas)
    assert "A CORUÑA" in lineas[0]


def test_una_cabecera_de_matriculaciones_se_ignora(tmp_path):
    cabecera = "Vehículos matriculados. Letras de la serie de la última matrícula asignada: ABC"
    ruta = zip_de(tmp_path / "export_mensual_mat_202401.zip", [cabecera, linea()])
    assert len(bronze.lineas_del_zip(ruta)) == 1


def test_si_alguna_linea_no_mide_714_caracteres_se_rechaza_el_fichero_entero(tmp_path):
    ruta = zip_de(tmp_path / "export_mensual_trf_202401.zip", [linea(), linea()[:-1], linea()])
    with pytest.raises(bronze.FormatoInesperado, match="1 líneas no miden 714"):
        bronze.lineas_del_zip(ruta)


def test_un_fichero_vacio_se_rechaza(tmp_path):
    ruta = zip_de(tmp_path / "export_mensual_trf_202401.zip", [])
    with pytest.raises(bronze.FormatoInesperado):
        bronze.lineas_del_zip(ruta)


def test_cada_campo_sale_de_su_posicion_y_se_guarda_como_texto_recortado(tmp_path):
    ruta = zip_de(
        tmp_path / "export_mensual_trf_202401.zip",
        [
            linea(
                marca_itv="SEAT",
                modelo_itv="IBIZA",
                cod_tipo="40",
                municipio="A CORUÑA",
                fec_tramite="15012024",
                kw_itv="  55.00",
            )
        ],
    )
    destino = tmp_path / "202401.parquet"
    assert bronze.microdatos_a_parquet(ruta, destino, "dgt/transferencias/x.zip") == 1
    fila = duckdb.sql(f"SELECT * FROM read_parquet('{destino.as_posix()}')").fetchone()
    columnas = [c[0] for c in duckdb.sql(f"SELECT * FROM read_parquet('{destino.as_posix()}')").description]
    fila = dict(zip(columnas, fila, strict=True))
    assert fila["marca_itv"] == "SEAT"
    assert fila["modelo_itv"] == "IBIZA"
    assert fila["municipio"] == "A CORUÑA"
    assert fila["kw_itv"] == "55.00"
    assert fila["fec_tramite"] == "15012024"
    assert fila["ind_baja_def"] is None  # un campo en blanco es null
    assert fila["_linea"] == 1
    assert fila["_fichero_origen"] == "dgt/transferencias/x.zip"
    assert len(columnas) == 69 + 3


def test_los_meses_ya_convertidos_no_se_rehacen_y_los_que_ya_no_estan_en_raw_se_quitan(tmp_path):
    raw, carpeta = tmp_path / "raw", tmp_path / "bronze"
    destino = raw / "dgt" / "transferencias"
    destino.mkdir(parents=True)
    zip_de(destino / "export_mensual_trf_202401.zip", [linea()])
    zip_de(destino / "export_mensual_trf_202402.zip", [linea(), linea()])
    tipo = TIPOS["transferencias"]

    assert bronze.actualizar_parquet_microdatos(raw, carpeta, tipo) == {"202401": 1, "202402": 2}
    assert bronze.actualizar_parquet_microdatos(raw, carpeta, tipo) == {}  # nada nuevo

    time.sleep(0.05)
    os.utime(destino / "export_mensual_trf_202402.zip")  # el ZIP de febrero se ha vuelto a descargar
    assert bronze.actualizar_parquet_microdatos(raw, carpeta, tipo) == {"202402": 2}

    (destino / "export_mensual_trf_202401.zip").unlink()
    bronze.actualizar_parquet_microdatos(raw, carpeta, tipo)
    assert [p.name for p in (carpeta / "dgt" / "transferencias").glob("*.parquet")] == ["202402.parquet"]


def test_la_vista_de_bronze_une_todos_los_meses_y_se_registra_la_carga(tmp_path):
    raw, carpeta = tmp_path / "raw", tmp_path / "bronze"
    origen = raw / "dgt" / "bajas"
    origen.mkdir(parents=True)
    zip_de(origen / "export_mensual_bajas_202401.zip", [linea(clave_tramite="3")])
    zip_de(origen / "export_mensual_bajas_202402.zip", [linea(clave_tramite="3"), linea(clave_tramite="6")])
    with bronze.conectar(tmp_path / "w.duckdb") as con:
        assert bronze.cargar_microdatos(con, raw, carpeta, TIPOS["bajas"]) == 3
        assert con.execute("SELECT count(DISTINCT _fichero_origen) FROM bronze.dgt_bajas").fetchone() == (2,)
        assert con.execute("SELECT tabla, filas FROM bronze._cargas").fetchall() == [("bronze.dgt_bajas", 3)]


def test_sin_microdatos_no_se_crea_la_vista(tmp_path):
    with bronze.conectar(tmp_path / "w.duckdb") as con, pytest.raises(FileNotFoundError):
        bronze.cargar_microdatos(con, tmp_path / "raw", tmp_path / "bronze", TIPOS["bajas"])


def test_la_tabla_mensual_de_la_dgt_se_pasa_a_formato_largo(tmp_path):
    raw = tmp_path
    sinteticos.escribir_tablas_dgt(raw)
    hoja = pd.read_excel(raw / "dgt_tablas" / "transferencias_tablas_2024.xlsx", sheet_name="V_2", header=None)
    largo = bronze.tabla_mensual_por_tipo(hoja, 2024)
    assert set(largo["mes"]) == set(range(1, 13))
    assert {"Turismos", "Total", "Tractores industriales"} <= set(
        largo["columna"]
    )  # los saltos de línea de la cabecera se quitan
    enero = largo[(largo["mes"] == 1) & (largo["columna"] == "Turismos")]["valor"].item()
    assert enero > 0
    # El total de cada mes es la suma de sus columnas
    por_mes = largo[largo["mes"] == 1].set_index("columna")["valor"]
    assert por_mes["Total"] == por_mes.drop("Total").sum()


def test_una_tabla_a_la_que_le_falta_un_mes_se_rechaza(tmp_path):
    sinteticos.escribir_tablas_dgt(tmp_path)
    hoja = pd.read_excel(tmp_path / "dgt_tablas" / "transferencias_tablas_2024.xlsx", sheet_name="V_2", header=None)
    hoja = hoja[hoja[0] != "Marzo"]
    with pytest.raises(bronze.FormatoInesperado, match="doce meses"):
        bronze.tabla_mensual_por_tipo(hoja, 2024)


def test_una_hoja_sin_la_cabecera_esperada_se_rechaza():
    with pytest.raises(bronze.FormatoInesperado, match="cabecera"):
        bronze.tabla_mensual_por_tipo(pd.DataFrame([["otra", 1], ["cosa", 2]]), 2024)


def test_la_serie_historica_ignora_las_notas_al_pie_y_quita_el_numero_de_nota(tmp_path):
    sinteticos.escribir_tablas_dgt(tmp_path)
    hoja = pd.read_excel(tmp_path / "dgt_tablas" / "transferencias_series_2024.xlsx", sheet_name=0, header=None)
    largo = bronze.serie_historica_por_tipo(hoja)
    assert largo["anio"].min() == 1990 and largo["anio"].max() == 2024
    assert "¹ Nota al pie." not in set(largo["columna"])
    assert {"Total", "Turismos"} <= set(largo["columna"])


def test_se_cargan_las_tablas_de_la_dgt_y_la_ultima_edicion_de_la_serie(raw_sintetico, tmp_path):
    raw, _ = raw_sintetico
    with bronze.conectar(tmp_path / "w.duckdb") as con:
        bronze.cargar_tablas_dgt(con, raw)
        assert con.execute("SELECT count(DISTINCT tramite) FROM bronze.dgt_tablas_mensuales").fetchone() == (2,)
        assert con.execute("SELECT min(anio), max(anio) FROM bronze.dgt_series_historicas").fetchone() == (1990, 2024)


def test_sin_tablas_de_la_dgt_se_avisa(tmp_path):
    with bronze.conectar(tmp_path / "w.duckdb") as con, pytest.raises(FileNotFoundError):
        bronze.cargar_tablas_dgt(con, tmp_path)


def test_eurostat_se_carga_con_la_ultima_ingesta(raw_sintetico, tmp_path):
    raw, _ = raw_sintetico
    with bronze.conectar(tmp_path / "w.duckdb") as con:
        filas = bronze.cargar_eurostat(con, raw)
        assert filas > 100
        minimo, maximo = con.execute("SELECT min(periodo), max(periodo) FROM bronze.eurostat_series").fetchone()
        assert (minimo, maximo) == ("2023-01", "2025-12")
        assert con.execute("SELECT count(DISTINCT _ingestado_en) FROM bronze.eurostat_series").fetchone() == (1,)


def test_sin_ninguna_ingesta_de_eurostat_se_avisa(tmp_path):
    (tmp_path / "eurostat").mkdir()
    with bronze.conectar(tmp_path / "w.duckdb") as con, pytest.raises(FileNotFoundError):
        bronze.cargar_eurostat(con, tmp_path)


def test_una_carga_sin_filas_es_un_error(tmp_path):
    with bronze.conectar(tmp_path / "w.duckdb") as con:
        con.execute("CREATE TABLE bronze.vacia (x INTEGER)")
        with pytest.raises(ValueError, match="no ha producido filas"):
            bronze._registrar(con, "bronze.vacia", "test")


def test_openpyxl_esta_disponible_para_leer_los_excel():
    assert openpyxl.__version__
