import zipfile
from pathlib import Path

import pytest
import requests

from coches_usados.ingest import dgt


class RespuestaFalsa:
    def __init__(self, estado: int = 200, contenido: bytes = b"", texto: str = ""):
        self.status_code = estado
        self._contenido = contenido
        self.text = texto

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def iter_content(self, tamanio):
        for i in range(0, len(self._contenido), tamanio):
            yield self._contenido[i : i + tamanio]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class SesionFalsa:
    """Responde con una lista de respuestas por URL, en orden, y anota las peticiones."""

    def __init__(self, respuestas: dict[str, list[RespuestaFalsa]]):
        self.respuestas = {url: list(r) for url, r in respuestas.items()}
        self.peticiones: list[str] = []

    def get(self, url, **kwargs):
        self.peticiones.append(url)
        cola = self.respuestas.get(url)
        if not cola:
            return RespuestaFalsa(404)
        return cola.pop(0) if len(cola) > 1 else cola[0]


def zip_con(
    nombre: str, contenido: bytes = b"linea\r\n", ruta: Path | None = None, interior: str | None = None
) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(f"{interior or nombre}.txt", contenido)
    return buffer.getvalue()


TRF = dgt.TIPOS["transferencias"]
LISTADO = """
<a href="https://www.dgt.es/microdatos/salida/2024/1/vehiculos/transferencias/export_mensual_trf_202401.zip">ene</a>
<a href="https://www.dgt.es/microdatos/salida/2024/2/vehiculos/transferencias/export_mensual_trf_202402.zip">feb</a>
<a href="https://www.dgt.es/microdatos/salida/2024/10/vehiculos/transferencias/export_mensual_trf_202410.zip">oct</a>
<a href="https://www.dgt.es/microdatos/salida/2024/3/vehiculos/transferencias/export_mensual_trf_202405.zip">incoherente</a>
<a href="https://www.dgt.es/microdatos/salida/2024/1/vehiculos/bajas/export_mensual_bajas_202401.zip">otro tipo</a>
"""


def test_las_url_siguen_el_patron_de_la_dgt():
    assert (
        dgt.url_mes(TRF, 2024, 2)
        == "https://www.dgt.es/microdatos/salida/2024/2/vehiculos/transferencias/export_mensual_trf_202402.zip"
    )
    assert dgt.nombre_fichero(dgt.TIPOS["bajas"], 2026, 8) == "export_mensual_bajas_202608"


def test_el_listado_oficial_da_los_meses_del_tipo_y_ordenados_sin_los_incoherentes():
    assert dgt.meses_del_listado(LISTADO, TRF) == [(2024, 1), (2024, 2), (2024, 10)]
    assert dgt.meses_del_listado(LISTADO, dgt.TIPOS["bajas"]) == [(2024, 1)]


def test_comprobar_zip_acepta_el_fichero_esperado(tmp_path):
    ruta = tmp_path / "a.zip"
    ruta.write_bytes(zip_con("export_mensual_trf_202401", b"x" * 10))
    assert dgt.comprobar_zip(ruta, "export_mensual_trf_202401") == 10


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        (b"no es un zip", "no es un ZIP"),
        (zip_con("otro_nombre"), "se esperaba"),
        (zip_con("export_mensual_trf_202401", b""), "vacío"),
    ],
)
def test_comprobar_zip_rechaza_lo_que_no_es_el_fichero_esperado(tmp_path, contenido, mensaje):
    ruta = tmp_path / "a.zip"
    ruta.write_bytes(contenido)
    with pytest.raises(dgt.FicheroNoValido, match=mensaje):
        dgt.comprobar_zip(ruta, "export_mensual_trf_202401")


def cliente(respuestas, intentos=3):
    dormidas: list[float] = []
    c = dgt.DgtClient(sesion=SesionFalsa(respuestas), intentos=intentos, espera=2.0, dormir=dormidas.append)
    return c, dormidas


def test_se_reintenta_un_404_pasajero_y_se_descarga_el_mes(tmp_path):
    url = dgt.url_mes(TRF, 2024, 1)
    c, dormidas = cliente({url: [RespuestaFalsa(404), RespuestaFalsa(200, zip_con("export_mensual_trf_202401"))]})
    ruta, cambiado = c.descargar_mes(TRF, 2024, 1, tmp_path)
    assert cambiado
    assert ruta.name == "export_mensual_trf_202401.zip"
    assert dormidas == [2.0]  # una espera antes del segundo intento
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob("*.nuevo"))


def test_una_descarga_corrupta_se_reintenta_y_no_deja_ficheros_a_medias(tmp_path):
    url = dgt.url_mes(TRF, 2024, 1)
    c, _ = cliente({url: [RespuestaFalsa(200, b"corrupto"), RespuestaFalsa(200, zip_con("export_mensual_trf_202401"))]})
    ruta, _ = c.descargar_mes(TRF, 2024, 1, tmp_path)
    assert zipfile.is_zipfile(ruta)


def test_si_todos_los_intentos_fallan_se_avisa_y_no_se_guarda_nada(tmp_path):
    url = dgt.url_mes(TRF, 2024, 1)
    c, dormidas = cliente({url: [RespuestaFalsa(500)]}, intentos=3)
    with pytest.raises(RuntimeError, match="tras 3 intentos"):
        c.descargar_mes(TRF, 2024, 1, tmp_path)
    assert dormidas == [2.0, 4.0]
    assert list(tmp_path.iterdir()) == []


def test_si_el_mes_no_ha_cambiado_se_conserva_la_copia_anterior(tmp_path):
    url = dgt.url_mes(TRF, 2024, 1)
    contenido = zip_con("export_mensual_trf_202401")
    c, _ = cliente({url: [RespuestaFalsa(200, contenido)]})
    primera, _ = c.descargar_mes(TRF, 2024, 1, tmp_path)
    antes = primera.stat().st_mtime_ns
    _, cambiado = c.descargar_mes(TRF, 2024, 1, tmp_path)
    assert not cambiado
    assert primera.stat().st_mtime_ns == antes  # no se reescribe: bronze no rehace ese mes


def test_si_el_mes_cambia_se_reemplaza(tmp_path):
    url = dgt.url_mes(TRF, 2024, 1)
    c, _ = cliente({url: [RespuestaFalsa(200, zip_con("export_mensual_trf_202401", b"a"))]})
    c.descargar_mes(TRF, 2024, 1, tmp_path)
    c.sesion.respuestas[url] = [RespuestaFalsa(200, zip_con("export_mensual_trf_202401", b"bb"))]
    ruta, cambiado = c.descargar_mes(TRF, 2024, 1, tmp_path)
    assert cambiado
    assert dgt.comprobar_zip(ruta, "export_mensual_trf_202401") == 2


def test_la_ingesta_descarga_lo_que_falta_y_revisa_los_dos_ultimos_publicados(tmp_path):
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    respuestas = {pagina: [RespuestaFalsa(200, texto=LISTADO)]}
    for mes in (1, 2, 10):
        respuestas[dgt.url_mes(TRF, 2024, mes)] = [RespuestaFalsa(200, zip_con(f"export_mensual_trf_2024{mes:02d}"))]
    c, _ = cliente(respuestas)
    carpeta = tmp_path / "trf"
    assert [f.name for f in dgt.ingerir_microdatos(c, TRF, (2024, 1), carpeta)] == [
        "export_mensual_trf_202401.zip",
        "export_mensual_trf_202402.zip",
        "export_mensual_trf_202410.zip",
    ]

    c.sesion.peticiones.clear()
    dgt.ingerir_microdatos(c, TRF, (2024, 1), carpeta)
    pedidos = [u.rsplit("_", 1)[1] for u in c.sesion.peticiones if u.endswith(".zip")]
    assert pedidos == ["202402.zip", "202410.zip"]  # enero ya estaba; febrero y octubre se revisan


def test_la_ingesta_respeta_el_mes_de_inicio(tmp_path):
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    respuestas = {pagina: [RespuestaFalsa(200, texto=LISTADO)]}
    respuestas[dgt.url_mes(TRF, 2024, 10)] = [RespuestaFalsa(200, zip_con("export_mensual_trf_202410"))]
    c, _ = cliente(respuestas)
    assert len(dgt.ingerir_microdatos(c, TRF, (2024, 10), tmp_path)) == 1


def test_un_listado_sin_enlaces_es_un_error_porque_la_pagina_ha_cambiado():
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    c, _ = cliente({pagina: [RespuestaFalsa(200, texto="<html>otra cosa</html>")]})
    with pytest.raises(ValueError, match="ha cambiado la página"):
        c.meses_publicados(TRF)


def _url_tabla(clave: str, anio: int) -> str:
    return f"{dgt.PUBLICACIONES}/{dgt.TABLAS_ANUALES[clave].format(anio=anio)}"


def _xlsx() -> RespuestaFalsa:
    return RespuestaFalsa(200, zip_con("[Content_Types]", interior="[Content_Types]"))


def test_una_tabla_se_guarda_con_su_nombre(tmp_path):
    c, _ = cliente({_url_tabla("bajas_tablas", 2025): [_xlsx()]})
    assert c.descargar_tabla("bajas_tablas", 2025, tmp_path) == tmp_path / "bajas_tablas_2025.xlsx"


def test_un_fichero_que_no_es_un_excel_se_rechaza(tmp_path):
    c, _ = cliente({_url_tabla("bajas_tablas", 2025): [RespuestaFalsa(200, b"<html>error</html>")]})
    with pytest.raises(RuntimeError, match="tras 3 intentos"):
        c.descargar_tabla("bajas_tablas", 2025, tmp_path)
    assert list(tmp_path.iterdir()) == []


def tablas(anios: tuple[int, ...], publicadas: dict[tuple[str, int], bool] | None = None):
    """Respuestas de una DGT en la que solo están las tablas indicadas (las demás fallan)."""
    respuestas = {}
    for anio in anios:
        for clave in dgt.TABLAS_ANUALES:
            if (publicadas or {}).get((clave, anio), True):
                respuestas[_url_tabla(clave, anio)] = [_xlsx()]
    return respuestas


def test_las_tablas_ya_descargadas_no_se_piden_de_nuevo(tmp_path):
    c, _ = cliente(tablas((2024, 2025)))
    assert len(dgt.ingerir_tablas(c, tmp_path, 2024, 2025)) == 5  # 2 y 2 de los años + la serie de 2025
    c.sesion.peticiones.clear()
    assert len(dgt.ingerir_tablas(c, tmp_path, 2024, 2025)) == 5
    assert c.sesion.peticiones == []


def test_la_serie_historica_solo_se_pide_en_su_ultima_edicion(tmp_path):
    c, _ = cliente(tablas((2024, 2025)))
    ficheros = dgt.ingerir_tablas(c, tmp_path, 2024, 2025)
    assert [f.name for f in ficheros if "series" in f.name] == ["transferencias_series_2025.xlsx"]


def test_si_las_tablas_del_ultimo_ano_no_estan_se_sigue_con_las_anteriores(tmp_path):
    publicadas = {(clave, 2026): False for clave in dgt.TABLAS_ANUALES}
    c, _ = cliente(tablas((2024, 2025, 2026), publicadas))
    ficheros = dgt.ingerir_tablas(c, tmp_path, 2024, 2026)
    assert {f.name for f in ficheros} == {
        "transferencias_tablas_2024.xlsx", "bajas_tablas_2024.xlsx",
        "transferencias_tablas_2025.xlsx", "bajas_tablas_2025.xlsx",
    }  # fmt: skip


def test_un_fallo_en_un_ano_anterior_es_un_error(tmp_path):
    c, _ = cliente(tablas((2024, 2025), {("bajas_tablas", 2024): False}))
    with pytest.raises(RuntimeError):
        dgt.ingerir_tablas(c, tmp_path, 2024, 2025)


def test_sin_ninguna_tabla_no_hay_con_que_cuadrar(tmp_path):
    c, _ = cliente({})
    with pytest.raises(RuntimeError, match="no se pueden cuadrar"):
        dgt.ingerir_tablas(c, tmp_path, 2025, 2025)


def test_las_tablas_del_respaldo_se_copian_sin_pedir_nada_a_la_dgt(tmp_path):
    respaldo = tmp_path / "respaldo"
    respaldo.mkdir()
    for clave in dgt.TABLAS_ANUALES:
        (respaldo / f"{clave}_2025.xlsx").write_bytes(b"copia oficial")
    c, _ = cliente({})  # cualquier petición daría 404
    ficheros = dgt.ingerir_tablas(c, tmp_path / "raw", 2025, 2025, respaldo=respaldo)
    assert len(ficheros) == 3
    assert c.sesion.peticiones == []
    assert (tmp_path / "raw" / "bajas_tablas_2025.xlsx").read_bytes() == b"copia oficial"


def test_lo_que_no_esta_en_el_respaldo_se_descarga(tmp_path):
    respaldo = tmp_path / "respaldo"
    respaldo.mkdir()
    (respaldo / "bajas_tablas_2024.xlsx").write_bytes(b"copia")
    (respaldo / "transferencias_tablas_2024.xlsx").write_bytes(b"copia")
    c, _ = cliente(tablas((2025,)))
    ficheros = dgt.ingerir_tablas(c, tmp_path / "raw", 2024, 2025, respaldo=respaldo)
    assert len(ficheros) == 5
    assert len(c.sesion.peticiones) == 3  # solo 2025: las dos tablas y la serie


def test_el_respaldo_del_repositorio_tiene_las_tablas_que_usa_el_pipeline():
    from coches_usados import definitions

    nombres = {f.name for f in definitions.REFERENCIA_DGT.glob("*.xlsx")}
    for anio in range(definitions.DESDE[0], 2026):
        assert f"transferencias_tablas_{anio}.xlsx" in nombres
        assert f"bajas_tablas_{anio}.xlsx" in nombres
    assert "transferencias_series_2025.xlsx" in nombres


def test_el_listado_se_reintenta_ante_errores_500_con_espera_creciente():
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    c, dormidas = cliente(
        {pagina: [RespuestaFalsa(500), RespuestaFalsa(500), RespuestaFalsa(200, texto=LISTADO)]}, intentos=4
    )
    assert c.meses_publicados(TRF) == [(2024, 1), (2024, 2), (2024, 10)]
    assert dormidas == [2.0, 4.0]


def test_si_el_listado_no_responde_nunca_se_avisa():
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    c, _ = cliente({pagina: [RespuestaFalsa(500)]}, intentos=2)
    with pytest.raises(RuntimeError, match="No se ha podido leer el listado"):
        c.meses_publicados(TRF)


def test_si_falla_la_revision_de_un_mes_ya_descargado_se_conserva_la_copia(tmp_path):
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    respuestas = {pagina: [RespuestaFalsa(200, texto=LISTADO)]}
    for mes in (1, 2, 10):
        respuestas[dgt.url_mes(TRF, 2024, mes)] = [RespuestaFalsa(200, zip_con(f"export_mensual_trf_2024{mes:02d}"))]
    c, _ = cliente(respuestas)
    dgt.ingerir_microdatos(c, TRF, (2024, 1), tmp_path)
    c.sesion.respuestas[dgt.url_mes(TRF, 2024, 10)] = [RespuestaFalsa(500)]
    ficheros = dgt.ingerir_microdatos(c, TRF, (2024, 1), tmp_path)
    assert len(ficheros) == 3  # octubre falla al revisarlo, pero ya estaba


def test_si_falla_un_mes_que_no_se_tenia_es_un_error(tmp_path):
    pagina = dgt.LISTADOS.format(pagina=TRF.pagina)
    respuestas = {pagina: [RespuestaFalsa(200, texto=LISTADO)], dgt.url_mes(TRF, 2024, 1): [RespuestaFalsa(500)]}
    c, _ = cliente(respuestas)
    with pytest.raises(RuntimeError, match="tras 3 intentos"):
        dgt.ingerir_microdatos(c, TRF, (2024, 1), tmp_path)
