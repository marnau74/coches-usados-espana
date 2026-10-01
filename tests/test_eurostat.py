import json
from datetime import date

import pytest

from coches_usados.ingest.eurostat import (
    EurostatClient,
    SerieEurostat,
    ingerir_series,
    observaciones,
    series_del_catalogo,
)
from tests.conftest import CATALOGO_EUROSTAT
from tests.sinteticos import _documento_eurostat
from tests.test_dgt import RespuestaFalsa


class SesionJson:
    def __init__(self, documento: dict):
        self.documento = documento
        self.peticiones: list[tuple[str, dict]] = []

    def get(self, url, params=None, **kwargs):
        self.peticiones.append((url, params))
        respuesta = RespuestaFalsa(200)
        respuesta.json = lambda: self.documento
        return respuesta


def test_el_catalogo_define_las_series_que_se_descargan():
    series = series_del_catalogo(CATALOGO_EUROSTAT)
    ids = {s.id for s in series}
    assert {"es_segunda_mano_indice", "es_segunda_mano_tasa"} <= ids
    segunda = next(s for s in series if s.id == "es_segunda_mano_indice")
    assert segunda.parametros == {"geo": "ES", "coicop18": "CP07112", "unit": "I25", "freq": "M"}


def test_las_observaciones_se_ordenan_y_los_meses_sin_valor_no_aparecen():
    documento = _documento_eurostat(
        [100.0, 101.5, 102.0] + [103.0] * 10, tasa=True, actualizado="2026-09-17T11:00:00+0200"
    )
    obs = observaciones(documento)
    assert obs[0][0] == "2024-01"  # la tasa anual no existe hasta el mes 13
    assert [o[0] for o in obs] == sorted(o[0] for o in obs)

    indice = observaciones(_documento_eurostat([100.0, 101.5], tasa=False, actualizado="x"))
    assert indice == [("2023-01", 100.0, None), ("2023-02", 101.5, None)]


def test_el_estado_provisional_se_conserva():
    documento = _documento_eurostat([100.0, 101.5], tasa=False, actualizado="x")
    documento["status"] = {"1": "p"}
    assert observaciones(documento)[1] == ("2023-02", 101.5, "p")


def test_una_respuesta_con_varias_series_es_un_error():
    documento = _documento_eurostat([100.0, 101.0], tasa=False, actualizado="x")
    documento["size"][3] = 2  # dos territorios
    with pytest.raises(ValueError, match="una sola serie"):
        observaciones(documento)


def test_el_cliente_pide_la_serie_y_rechaza_respuestas_sin_datos():
    serie = SerieEurostat("s", "prc_hicp_minr", "ES", "CP07112", "I25")
    sesion = SesionJson(_documento_eurostat([100.0, 101.0], tasa=False, actualizado="x"))
    EurostatClient(sesion).serie(serie)
    url, params = sesion.peticiones[0]
    assert url.endswith("/data/prc_hicp_minr")
    assert params["coicop18"] == "CP07112"

    vacia = _documento_eurostat([100.0], tasa=False, actualizado="x")
    vacia["value"] = {}
    with pytest.raises(ValueError, match="no devuelve datos"):
        EurostatClient(SesionJson(vacia)).serie(serie)


def test_la_ingesta_guarda_una_respuesta_por_serie_en_la_carpeta_del_dia(tmp_path):
    series = [SerieEurostat("a", "c", "ES", "X", "I25"), SerieEurostat("b", "c", "ES", "Y", "I25")]
    sesion = SesionJson(_documento_eurostat([100.0, 101.0], tasa=False, actualizado="x"))
    rutas = ingerir_series(EurostatClient(sesion), series, tmp_path, date(2026, 10, 1))
    assert [r.relative_to(tmp_path).as_posix() for r in rutas] == ["2026-10-01/a.json", "2026-10-01/b.json"]
    assert json.loads(rutas[0].read_text(encoding="utf-8"))["id"][-1] == "time"
