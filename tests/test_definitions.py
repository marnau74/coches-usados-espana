import dagster as dg
import pytest

from coches_usados import definitions


@pytest.fixture(scope="module")
def grafo():
    return definitions.defs.resolve_asset_graph()


def claves(grafo):
    return {"/".join(k.path) for k in grafo.get_all_asset_keys()}


def nombres_de_modelos(grafo):
    """Los assets de dbt se identifican por esquema y nombre (gold/fct_...)."""
    return {k.path[-1] for k in grafo.get_all_asset_keys() if k.path[0] in ("silver", "gold")}


def test_el_grafo_une_la_descarga_con_bronze_y_los_modelos_de_dbt(grafo):
    todas = claves(grafo)
    assert {"raw_dgt_microdatos", "raw_dgt_tablas", "raw_eurostat"} <= todas
    assert {
        "bronze/dgt_matriculaciones", "bronze/dgt_transferencias", "bronze/dgt_bajas",
        "bronze/dgt_tablas_mensuales", "bronze/dgt_series_historicas", "bronze/eurostat_series",
    } <= todas  # fmt: skip
    assert {"fct_tramites_mensual", "fct_modelos_mensual", "int_dgt__turismos"} <= nombres_de_modelos(grafo)


def test_cada_capa_depende_de_la_anterior(grafo):
    def padres(clave):
        return {"/".join(k.path) for k in grafo.get(dg.AssetKey(clave.split("/"))).parent_keys}

    assert padres("bronze/dgt_transferencias") == {"raw_dgt_microdatos"}
    assert padres("bronze/eurostat_series") == {"raw_eurostat"}
    assert "bronze/dgt_transferencias" in padres("silver/stg_dgt__transferencias")
    assert "silver/stg_dgt__transferencias" in padres("silver/int_dgt__turismos")
    assert "silver/int_dgt__turismos" in padres("gold/fct_tramites_mensual")


def test_los_tests_de_dbt_ligados_a_un_modelo_son_comprobaciones_del_grafo(grafo):
    """Los que cruzan varios modelos (los de cuadre) corren igualmente en `dbt build` y
    detienen la ejecución si fallan, pero Dagster no los asigna a un asset."""
    nombres = {c.name for c in grafo.asset_check_keys}
    assert "assert_campos_de_turismos_informados" in nombres
    assert any(n.startswith("unique_combination_fct_tramites_mensual") for n in nombres)
    assert any(n.startswith("relationships_fct_tramites_mensual_provincia_id") for n in nombres)
    assert "eurostat_datos_recientes" in nombres


def test_hay_un_trabajo_mensual_programado_para_cuando_las_fuentes_ya_publicaron():
    assert definitions.pipeline_mensual.name == "pipeline_mensual"
    assert definitions.ejecucion_mensual.cron_schedule == "0 7 20 * *"
    assert definitions.ejecucion_mensual.execution_timezone == "Europe/Madrid"


def test_el_primer_mes_descargado_coincide_con_la_ventana_de_dbt():
    import yaml

    proyecto = yaml.safe_load((definitions.RAIZ / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))
    anio, mes = definitions.DESDE
    assert proyecto["vars"]["inicio_ventana"] == f"{anio}-{mes:02d}-01"


def test_el_trabajo_se_ejecuta_en_un_solo_proceso_porque_duckdb_tiene_un_unico_escritor():
    assert definitions.pipeline_mensual.executor_def is dg.in_process_executor
