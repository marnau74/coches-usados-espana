"""Cliente de la API de difusión de Eurostat (JSON-stat 2.0).

Se usan índices de precios de consumo armonizados (IPCA) de la clasificación ECOICOP 2
(conjunto `prc_hicp_minr`, base 2025 = 100), que Eurostat publica cada mes hacia mediados
del mes siguiente. La serie clave es la de automóviles de segunda mano (CP07112): es la
medida oficial de cómo evolucionan sus precios en España. No es un precio en euros.

Cada serie se guarda tal cual la devuelve la API, en una carpeta por fecha de ingesta.
Las series a descargar están en dbt/seeds/series_eurostat.csv.

Licencia de los datos: reutilización libre citando la fuente (Eurostat).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from coches_usados.ingest.http import TIEMPO_MAXIMO, sesion_con_reintentos

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{conjunto}"


@dataclass(frozen=True)
class SerieEurostat:
    id: str
    conjunto: str
    geo: str
    coicop: str
    unidad: str

    @property
    def parametros(self) -> dict[str, str]:
        return {"geo": self.geo, "coicop18": self.coicop, "unit": self.unidad, "freq": "M"}


def series_del_catalogo(catalogo: Path) -> list[SerieEurostat]:
    with catalogo.open(encoding="utf-8") as f:
        return [
            SerieEurostat(fila["id"], fila["conjunto"], fila["geo"], fila["coicop"], fila["unidad"])
            for fila in csv.DictReader(f)
        ]


def observaciones(documento: dict) -> list[tuple[str, float, str | None]]:
    """(periodo AAAA-MM, valor, estado) de una respuesta JSON-stat con una sola serie.

    En JSON-stat los valores van indexados por la posición en la dimensión tiempo; un
    periodo sin valor no aparece en `value`. El estado (p. ej. «p» provisional) es opcional.
    """
    dimensiones = documento["id"]
    tamanios = documento["size"]
    for dim, tam in zip(dimensiones, tamanios, strict=True):
        if dim != "time" and tam != 1:
            raise ValueError(f"La respuesta tiene {tam} valores en la dimensión {dim}: se esperaba una sola serie")
    tiempo = documento["dimension"]["time"]["category"]["index"]
    por_posicion = {pos: periodo for periodo, pos in tiempo.items()}
    valores = documento.get("value", {})
    estados = documento.get("status", {})
    if isinstance(valores, list):  # JSON-stat permite también una lista densa
        valores = {str(i): v for i, v in enumerate(valores) if v is not None}
    return sorted(
        (por_posicion[int(pos)], float(valor), estados.get(pos)) for pos, valor in valores.items() if valor is not None
    )


class EurostatClient:
    def __init__(self, sesion: requests.Session | None = None):
        self.sesion = sesion or sesion_con_reintentos()

    def serie(self, serie: SerieEurostat) -> dict:
        respuesta = self.sesion.get(API.format(conjunto=serie.conjunto), params=serie.parametros, timeout=TIEMPO_MAXIMO)
        respuesta.raise_for_status()
        documento = respuesta.json()
        if not observaciones(documento):
            raise ValueError(f"Eurostat no devuelve datos para la serie {serie.id}")
        return documento


def ingerir_series(cliente: EurostatClient, series: list[SerieEurostat], raw: Path, fecha_ingesta: date) -> list[Path]:
    """Guarda cada serie en raw/AAAA-MM-DD/<id>.json y devuelve las rutas."""
    carpeta = raw / fecha_ingesta.isoformat()
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for serie in series:
        destino = carpeta / f"{serie.id}.json"
        destino.write_text(json.dumps(cliente.serie(serie), ensure_ascii=False), encoding="utf-8")
        rutas.append(destino)
    return rutas
