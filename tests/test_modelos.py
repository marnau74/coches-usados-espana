"""Los modelos de dbt sobre los datos sintéticos: cada cifra de gold se comprueba contra lo que
el generador fabricó (ver tests/sinteticos.py)."""

import shutil
from pathlib import Path

import duckdb
import pytest

from tests.conftest import ejecutar_dbt
from tests.sinteticos import PLAN_TRANSFERENCIAS


@pytest.fixture(scope="module")
def con(warehouse_sintetico):
    with duckdb.connect(str(warehouse_sintetico), read_only=True) as conexion:
        yield conexion


def uno(con, sql, *params):
    return con.execute(sql, list(params)).fetchone()[0]


def test_las_transferencias_de_turismos_son_las_fabricadas_menos_las_anteriores_a_la_ventana(con):
    # 12 meses: 30 + mes turismos, más una fila tardía por mes (la de enero es de 2023 y se descarta)
    esperadas = sum(PLAN_TRANSFERENCIAS["40"] + m for m in range(1, 13)) + 11
    assert uno(con, "SELECT sum(tramites) FROM gold.fct_tramites_mensual WHERE tramite = 'transferencia'") == esperadas


def test_el_tramite_tardio_se_asigna_al_mes_de_su_fecha_no_al_del_fichero(con):
    # febrero lleva 30 + 2 propios y 1 tardío que llegó en el fichero de marzo
    assert (
        uno(
            con,
            "SELECT sum(tramites) FROM gold.fct_tramites_mensual WHERE tramite='transferencia' AND fecha_id = 202402",
        )
        == 30 + 2 + 1
    )


def test_solo_cuentan_las_matriculaciones_ordinarias_de_turismos(con):
    # 20 al mes; la rematriculación (clave 5) y la moto no cuentan
    assert uno(con, "SELECT sum(tramites) FROM gold.fct_tramites_mensual WHERE tramite = 'matriculacion'") == 20 * 12


def test_solo_cuentan_las_bajas_definitivas_y_la_temporal_queda_fuera(con):
    # por mes: 12 voluntarias + 2 «otros» + 3 exportación + 1 de oficio (la temporal, clave 6, no cuenta)
    por_motivo = dict(
        con.execute(
            "SELECT motivo_baja, sum(tramites) FROM gold.fct_tramites_mensual WHERE tramite='baja' GROUP BY 1"
        ).fetchall()
    )
    assert por_motivo == {"voluntaria": 12 * 12, "otros_motivos": 2 * 12, "exportacion": 3 * 12, "de_oficio": 1 * 12}


def test_la_provincia_sin_dato_queda_como_desconocida_y_todas_existen_en_la_dimension(con):
    assert (
        uno(
            con,
            "SELECT count(*) FROM gold.fct_tramites_mensual f LEFT JOIN gold.dim_provincia p USING (provincia_id) WHERE p.provincia_id IS NULL",
        )
        == 0
    )


def test_el_combustible_sale_de_la_categoria_electrica_antes_que_de_la_propulsion(con):
    combustibles = {
        c for (c,) in con.execute("SELECT DISTINCT combustible_id FROM gold.fct_tramites_mensual").fetchall()
    }
    # (propulsión, categoría) fabricados: gasolina, diésel, híbrido (0+HEV), eléctrico (2+BEV), enchufable (1+PHEV), gas (4)
    assert combustibles == {"gasolina", "diesel", "hibrido", "electrico", "hibrido_enchufable", "gas"}


def test_la_marca_y_el_modelo_se_normalizan(con):
    modelos = set(
        con.execute("SELECT DISTINCT marca, modelo FROM gold.fct_modelos_mensual WHERE modelo <> 'OTROS'").fetchall()
    )
    assert ("SEAT", "IBIZA") in modelos  # versión y cilindrada fuera
    assert ("NISSAN", "QASHQAI") in modelos  # marca repetida delante
    assert ("MERCEDES-BENZ", "A") in modelos  # alias de marca y clase
    assert ("BMW", "SERIE 3") in modelos  # 320D es de la serie 3
    assert ("CITROEN", "C3") in modelos  # «NUEVO C3»
    assert ("VOLKSWAGEN", "GOLF") in modelos
    assert not any(marca == "MERCEDES" for marca, _ in modelos)


def test_la_antiguedad_nunca_es_negativa_y_se_agrupa_en_tramos_conocidos(con):
    assert uno(con, "SELECT min(antiguedad_anios) FROM silver.int_dgt__turismos") >= 0
    tramos = {t for (t,) in con.execute("SELECT DISTINCT tramo_antiguedad FROM gold.fct_tramites_mensual").fetchall()}
    assert tramos <= {"sin_dato", "0_2", "3_5", "6_9", "10_14", "15_19", "20_o_mas"}


def test_la_eñe_de_los_municipios_sobrevive_hasta_staging(con):
    assert uno(con, "SELECT count(*) FROM bronze.dgt_transferencias WHERE municipio = 'A CORUÑA'") > 0


def test_los_dos_ultimos_meses_son_provisionales(con):
    provisionales = [
        m for (m,) in con.execute("SELECT fecha_id FROM gold.dim_fecha WHERE provisional ORDER BY 1").fetchall()
    ]
    assert provisionales == [202411, 202412]


def test_la_variacion_de_precios_se_calcula_del_indice(con):
    fila = con.execute(
        "SELECT variacion_anual, variacion_anual_calculada FROM gold.fct_precios_indice_mensual "
        "WHERE territorio = 'espana' AND producto = 'automoviles_segunda_mano' AND fecha_id = 202501"
    ).fetchone()
    assert fila[0] == pytest.approx(fila[1], abs=0.15)
    assert fila[1] is not None


def test_la_serie_historica_llega_hasta_el_ultimo_ano_y_sin_totales(con):
    assert con.execute("SELECT min(anio), max(anio) FROM gold.fct_titularidad_anual").fetchone() == (1990, 2024)
    assert uno(con, "SELECT count(*) FROM gold.fct_titularidad_anual WHERE grupo_vehiculo = 'total'") == 0


# --- Los tests de cuadre fallan cuando deben --------------------------------------------------


@pytest.fixture
def warehouse_manipulable(warehouse_sintetico, tmp_path):
    copia = tmp_path / "warehouse.duckdb"
    shutil.copy(warehouse_sintetico, copia)
    # las vistas de bronze apuntan a los Parquet por ruta absoluta: siguen valiendo con la copia
    return copia


def _ejecutar_test(warehouse: Path, nombre: str) -> bool:
    return ejecutar_dbt("test", "--select", nombre, warehouse=warehouse).returncode == 0


def test_el_cuadre_de_transferencias_pasa_con_los_datos_buenos(warehouse_manipulable):
    assert _ejecutar_test(warehouse_manipulable, "assert_transferencias_cuadran_con_dgt")


def test_el_cuadre_de_transferencias_falla_si_la_tabla_oficial_se_desvia_un_2_por_ciento(warehouse_manipulable):
    with duckdb.connect(str(warehouse_manipulable)) as con:
        con.execute(
            "UPDATE bronze.dgt_tablas_mensuales SET valor = round(valor * 1.02) "
            "WHERE tramite = 'transferencias' AND columna = 'Turismos' AND mes = 3"
        )
    assert not _ejecutar_test(warehouse_manipulable, "assert_transferencias_cuadran_con_dgt")


def test_el_cuadre_de_bajas_falla_si_se_pierden_bajas_en_los_microdatos(warehouse_manipulable):
    with duckdb.connect(str(warehouse_manipulable)) as con:
        con.execute(
            "UPDATE bronze.dgt_tablas_mensuales SET valor = valor + 5 WHERE tramite = 'bajas' AND columna = 'Turismos' AND mes = 6"
        )
    assert not _ejecutar_test(warehouse_manipulable, "assert_bajas_cuadran_con_dgt")


def test_falta_un_fichero_mensual_lo_detecta_el_test_de_completitud(warehouse_manipulable):
    # En el warehouse hay un fichero por mes: se simula que febrero de bajas llegó vacío
    with duckdb.connect(str(warehouse_manipulable)) as con:
        con.execute(
            "CREATE OR REPLACE TABLE bronze.dgt_bajas_cortada AS SELECT * FROM bronze.dgt_bajas WHERE _fichero_origen NOT LIKE '%202402%'"
        )
        con.execute("CREATE OR REPLACE VIEW bronze.dgt_bajas AS SELECT * FROM bronze.dgt_bajas_cortada")
    assert not _ejecutar_test(warehouse_manipulable, "assert_microdatos_completos")
