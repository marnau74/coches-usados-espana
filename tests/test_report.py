import json
import re

import duckdb
import pytest

from coches_usados.report import build_site, indicadores


@pytest.fixture(scope="module")
def con(warehouse_sintetico):
    with duckdb.connect(str(warehouse_sintetico), read_only=True) as conexion:
        yield conexion


def test_meta_da_el_periodo_los_anios_completos_y_lo_provisional(con):
    meta = indicadores.meta(con)
    assert meta["primer_mes"] == "2024-01"
    assert meta["ultimo_mes"] == "2024-12"
    assert meta["provisional_desde"] == "2024-11"
    assert meta["anios_completos"] == []  # los dos últimos meses son provisionales: ningún año está completo
    assert meta["ultimo_mes_eurostat"] == "2025-12"


def test_la_serie_mensual_suma_lo_mismo_que_gold(con):
    serie = indicadores.serie_mensual(con)
    (esperado,) = con.execute("SELECT sum(tramites) FROM gold.fct_tramites_mensual").fetchone()
    assert sum(d["tramites"] for d in serie) == esperado
    assert {d["tramite"] for d in serie} == {"matriculacion", "transferencia", "baja"}


def test_las_provincias_incluyen_siempre_la_de_murcia_y_estan_ordenadas(con):
    filas = indicadores.provincias(con, 2024, cuantas=2)
    assert [f["puesto"] for f in filas] == sorted(f["puesto"] for f in filas)
    assert "MU" in {f["provincia_id"] for f in filas}
    assert all(f["tramites"] > 0 for f in filas)


def test_los_modelos_top_no_incluyen_el_cajon_de_sastre(con):
    assert "OTROS" not in {m["modelo"] for m in indicadores.modelos_top(con, 2024)}


def test_el_cuadre_se_calcula_igual_que_los_tests_de_dbt(con):
    cuadre = indicadores.cuadre(con)
    assert cuadre["meses_transferencias"] == 12
    assert cuadre["dif_max_transferencias"] == 0  # los datos sintéticos cuadran exactamente
    assert cuadre["meses_bajas"] == 12


def test_los_precios_empiezan_en_2015_o_antes_y_traen_las_tres_series_de_espana(con):
    productos = {p["producto"] for p in indicadores.precios(con) if p["territorio"] == "espana"}
    assert productos == {"automoviles_segunda_mano", "automoviles_nuevos", "general"}


def test_calcular_devuelve_todo_lo_que_pinta_la_plantilla(con, monkeypatch):
    # con datos sintéticos no hay ningún año completo: se simula uno para probar el conjunto
    original = indicadores.meta
    monkeypatch.setattr(indicadores, "meta", lambda c: {**original(c), "anios_completos": [2024]})
    datos = indicadores.calcular(con)
    plantilla = (build_site.PLANTILLA).read_text(encoding="utf-8")
    for clave in datos:
        assert f"DATOS.{clave}" in plantilla, f"la plantilla no usa «{clave}»"
    json.dumps(datos, default=str)


def test_la_web_se_genera_sin_marcador_y_con_los_datos_incrustados(warehouse_sintetico, tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "calcular", lambda c: {"meta": {"x": "</script><b>"}, "serie": []})
    destino = build_site.generar(str(warehouse_sintetico), tmp_path)
    html = destino.read_text(encoding="utf-8")
    assert build_site.MARCADOR not in html
    assert "</script><b>" not in html  # los datos no pueden cerrar el script
    incrustado = re.search(r"const DATOS = (\{.*?\});\n", html, re.S).group(1)
    assert json.loads(incrustado)["meta"]["x"] == "</script><b>"


def test_una_plantilla_sin_marcador_es_un_error(warehouse_sintetico, tmp_path, monkeypatch):
    plantilla = tmp_path / "p.html"
    plantilla.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(build_site, "PLANTILLA", plantilla)
    with pytest.raises(ValueError, match="marcador"):
        build_site.generar(str(warehouse_sintetico), tmp_path)
