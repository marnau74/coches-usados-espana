"""Capa bronze: lleva la capa raw a DuckDB y Parquet, sin interpretar nada.

Reglas de esta capa (ver docs/adr/0003-arquitectura-por-capas.md):
  - Una tabla por fuente con los datos tal cual: sin filtrar, sin traducir códigos y sin
    corregir nada. Los microdatos de la DGT se cortan por las posiciones del diseño de
    registro oficial y se guardan como texto recortado; tipar las fechas y los números es
    trabajo de staging, donde los tests miden cuántos valores no se pueden convertir.
  - Cada fila lleva `_fichero_origen` y `_ingestado_en` para saber de dónde sale.
  - Los microdatos (unos 13 millones de filas) se guardan en un Parquet por mes y tipo de
    trámite, que solo se rehace si el ZIP es más nuevo, y el warehouse los lee con vistas.
    El resto de tablas, pequeñas, se reemplazan enteras en cada carga.
  - Cada carga deja constancia en `bronze._cargas`.

Uso: python -m coches_usados.bronze
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from coches_usados.ingest.dgt import TIPOS, TipoTramite
from coches_usados.ingest.diseno_registro import CAMPOS, CODIFICACION, LONGITUD_LINEA
from coches_usados.ingest.eurostat import observaciones

WAREHOUSE = Path("data/warehouse.duckdb")
RAW = Path("data/raw")
BRONZE = Path("data/bronze")

PATRON_INGESTA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATRON_MES = re.compile(r"^export_mensual_[a-z]+_(\d{6})\.zip$")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")  # fmt: skip


class FormatoInesperado(Exception):
    """El fichero no tiene el formato que se espera de la fuente."""


def conectar(ruta: Path | str = WAREHOUSE) -> duckdb.DuckDBPyConnection:
    """Abre el warehouse y se asegura de que existen el esquema y el registro de cargas."""
    if ruta != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ruta))
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bronze._cargas (
            tabla VARCHAR NOT NULL,
            filas BIGINT NOT NULL,
            origen VARCHAR NOT NULL,
            cargado_en TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    return con


def _registrar(con: duckdb.DuckDBPyConnection, tabla: str, origen: str) -> int:
    filas = con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
    if filas == 0:
        raise ValueError(f"La carga de {tabla} desde {origen} no ha producido filas")
    con.execute("INSERT INTO bronze._cargas (tabla, filas, origen) VALUES (?, ?, ?)", [tabla, filas, origen])
    return filas


# --- Microdatos de la DGT ---------------------------------------------------------------


def lineas_del_zip(ruta: Path) -> list[str]:
    """Líneas del único fichero de texto del ZIP, decodificadas en Latin-1 y comprobadas.

    Todas las líneas deben medir exactamente lo que dice el diseño de registro: si no, el
    formato ha cambiado y cortar por posiciones daría columnas desplazadas sin avisar.
    (El código de la versión anterior de este proyecto leía el fichero como UTF-8 y
    descartaba en silencio las líneas con eñes o tildes: un 5 % de los trámites.)
    """
    with zipfile.ZipFile(ruta) as z:
        (nombre,) = z.namelist()
        texto = z.read(nombre).decode(CODIFICACION)
    lineas = texto.split("\n")
    if lineas and lineas[-1] in ("", "\r"):
        lineas.pop()
    lineas = [linea.removesuffix("\r") for linea in lineas]
    # El documento de la DGT avisa de una cabecera en los ficheros diarios de matriculaciones.
    if lineas and lineas[0].startswith("Veh") and len(lineas[0]) != LONGITUD_LINEA:
        lineas.pop(0)
    if not lineas:
        raise FormatoInesperado(f"{ruta.name}: no tiene ninguna línea")
    malas = [i for i, linea in enumerate(lineas, start=1) if len(linea) != LONGITUD_LINEA]
    if malas:
        ejemplos = ", ".join(f"línea {i} ({len(lineas[i - 1])} caracteres)" for i in malas[:3])
        raise FormatoInesperado(
            f"{ruta.name}: {len(malas)} líneas no miden {LONGITUD_LINEA} caracteres ({ejemplos}). "
            "¿Ha cambiado el diseño de registro de la DGT?"
        )
    return lineas


def microdatos_a_parquet(zip_origen: Path, destino: Path, origen: str) -> int:
    """Corta cada línea por los campos del diseño de registro y guarda un Parquet."""
    lineas = lineas_del_zip(zip_origen)
    # El número de línea va en la tabla: DuckDB lee en paralelo y no garantiza el orden.
    tabla_lineas = pa.table(  # noqa: F841 (la lee DuckDB por nombre)
        {"linea": pa.array(lineas, type=pa.string()), "_linea": pa.array(range(1, len(lineas) + 1), type=pa.int32())}
    )
    columnas = ",\n".join(f"nullif(trim(substr(linea, {c.inicio}, {c.longitud})), '') AS {c.nombre}" for c in CAMPOS)
    ingestado = date.fromtimestamp(zip_origen.stat().st_mtime).isoformat()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".parquet.part")
    with duckdb.connect() as con:
        con.execute("SET enable_progress_bar = false")
        con.execute(
            f"""
            COPY (
                SELECT
                    {columnas},
                    _linea,
                    $origen AS _fichero_origen,
                    $ingestado::DATE AS _ingestado_en
                FROM tabla_lineas
            ) TO '{temporal.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
            """,
            {"origen": origen, "ingestado": ingestado},
        )
    temporal.replace(destino)
    return len(lineas)


def actualizar_parquet_microdatos(raw: Path, bronze: Path, tipo: TipoTramite) -> dict[str, int]:
    """Rehace el Parquet de cada mes cuyo ZIP es más nuevo que su Parquet (o no lo tiene).
    Devuelve las filas de cada mes rehecho."""
    carpeta_raw = raw / "dgt" / tipo.nombre
    carpeta_bronze = bronze / "dgt" / tipo.nombre
    rehechos = {}
    for zip_mes in sorted(carpeta_raw.glob("export_mensual_*.zip")):
        coincidencia = PATRON_MES.match(zip_mes.name)
        if not coincidencia:
            continue
        destino = carpeta_bronze / f"{coincidencia[1]}.parquet"
        if destino.exists() and destino.stat().st_mtime >= zip_mes.stat().st_mtime:
            continue
        origen = f"dgt/{tipo.nombre}/{zip_mes.name}"
        rehechos[coincidencia[1]] = microdatos_a_parquet(zip_mes, destino, origen)
    # Un Parquet sin su ZIP sería un mes que ya no está en raw: se quita para no mezclar.
    zips = {PATRON_MES.match(z.name)[1] for z in carpeta_raw.glob("export_mensual_*.zip") if PATRON_MES.match(z.name)}
    for huerfano in carpeta_bronze.glob("*.parquet"):
        if huerfano.stem not in zips:
            huerfano.unlink()
    return rehechos


def cargar_microdatos(con: duckdb.DuckDBPyConnection, raw: Path, bronze: Path, tipo: TipoTramite) -> int:
    """bronze.dgt_<tipo>: vista sobre los Parquet mensuales de ese tipo de trámite."""
    actualizar_parquet_microdatos(raw, bronze, tipo)
    carpeta = (bronze / "dgt" / tipo.nombre).resolve()
    if not any(carpeta.glob("*.parquet")):
        raise FileNotFoundError(f"No hay microdatos de {tipo.nombre} en {raw / 'dgt' / tipo.nombre}")
    patron = (carpeta / "*.parquet").as_posix().replace("'", "''")  # una vista no admite parámetros
    tabla = f"bronze.dgt_{tipo.nombre}"
    con.execute(f"CREATE OR REPLACE VIEW {tabla} AS SELECT * FROM read_parquet('{patron}')")
    return _registrar(con, tabla, f"dgt/{tipo.nombre}")


# --- Tablas estadísticas anuales de la DGT ------------------------------------------------


def _texto(valor) -> str:
    return re.sub(r"\s+", " ", str(valor)).strip() if pd.notna(valor) else ""


def _fila_cabecera(hoja: pd.DataFrame, primera: str) -> int:
    for i, valor in enumerate(hoja.iloc[:, 0]):
        if _texto(valor).lower() == primera:
            return i
    raise FormatoInesperado(f"No se encuentra la cabecera «{primera}»")


def tabla_mensual_por_tipo(hoja: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Tabla «distribuidos por meses y tipos» de la DGT en formato largo: una fila por mes
    y columna publicada (los totales incluidos, tal cual)."""
    cabecera = _fila_cabecera(hoja, "mes")
    columnas = [_texto(v) for v in hoja.iloc[cabecera]]
    filas = []
    for _, fila in hoja.iloc[cabecera + 1 :].iterrows():
        etiqueta = _texto(fila.iloc[0]).lower()
        if etiqueta not in MESES:
            continue
        mes = MESES.index(etiqueta) + 1
        for columna, valor in zip(columnas[1:], fila.iloc[1:], strict=True):
            if columna and pd.notna(valor):
                filas.append({"anio": anio, "mes": mes, "columna": columna, "valor": int(valor)})
    if {f["mes"] for f in filas} != set(range(1, 13)):
        raise FormatoInesperado(f"La tabla mensual de {anio} no tiene los doce meses")
    return pd.DataFrame(filas)


def serie_historica_por_tipo(hoja: pd.DataFrame) -> pd.DataFrame:
    """Serie histórica anual «por tipos» en formato largo: una fila por año y columna."""
    cabecera = _fila_cabecera(hoja, "año")
    columnas = [_texto(v) for v in hoja.iloc[cabecera]]
    filas = []
    for _, fila in hoja.iloc[cabecera + 1 :].iterrows():
        anio = pd.to_numeric(fila.iloc[0], errors="coerce")
        if pd.isna(anio):
            continue
        for columna, valor in zip(columnas[1:], fila.iloc[1:], strict=True):
            if columna and pd.notna(valor):
                filas.append({"anio": int(anio), "columna": columna, "valor": int(valor)})
    if not filas:
        raise FormatoInesperado("La serie histórica no tiene ningún año")
    return pd.DataFrame(filas)


# Hoja de cada fichero que se carga y qué tabla de bronze alimenta.
HOJAS_MENSUALES = {"transferencias_tablas": ("V_2", "transferencias"), "bajas_tablas": ("V_3_Bajas", "bajas")}
HOJAS_HISTORICAS = {"transferencias_series": ("cambios_Titularidad", "transferencias")}
PATRON_TABLA = re.compile(r"^([a-z_]+)_(\d{4})\.xlsx$")


def cargar_tablas_dgt(con: duckdb.DuckDBPyConnection, raw: Path = RAW) -> int:
    """bronze.dgt_tablas_mensuales y bronze.dgt_series_historicas, desde los Excel de la
    DGT. De cada serie histórica se usa solo la publicación más reciente."""
    carpeta = raw / "dgt_tablas"
    mensuales, historicas = [], {}
    for fichero in sorted(carpeta.glob("*.xlsx")):
        coincidencia = PATRON_TABLA.match(fichero.name)
        if not coincidencia:
            continue
        clave, anio = coincidencia[1], int(coincidencia[2])
        ingestado = date.fromtimestamp(fichero.stat().st_mtime)
        if clave in HOJAS_MENSUALES:
            hoja, tramite = HOJAS_MENSUALES[clave]
            tabla = tabla_mensual_por_tipo(pd.read_excel(fichero, sheet_name=hoja, header=None), anio)
            tabla = tabla.assign(tramite=tramite, _fichero_origen=f"dgt_tablas/{fichero.name}", _ingestado_en=ingestado)
            mensuales.append(tabla)
        elif clave in HOJAS_HISTORICAS:
            hoja, tramite = HOJAS_HISTORICAS[clave]
            tabla = serie_historica_por_tipo(pd.read_excel(fichero, sheet_name=hoja, header=None))
            tabla = tabla.assign(tramite=tramite, _fichero_origen=f"dgt_tablas/{fichero.name}", _ingestado_en=ingestado)
            historicas[tramite] = tabla  # los ficheros van en orden: queda el último año
    if not mensuales or not historicas:
        raise FileNotFoundError(f"Faltan tablas estadísticas de la DGT en {carpeta}")
    tablas_mensuales = pd.concat(mensuales, ignore_index=True)  # noqa: F841
    series = pd.concat(historicas.values(), ignore_index=True)  # noqa: F841
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze.dgt_tablas_mensuales AS
        SELECT tramite::VARCHAR AS tramite, anio::SMALLINT AS anio, mes::SMALLINT AS mes,
               columna::VARCHAR AS columna, valor::BIGINT AS valor,
               _fichero_origen::VARCHAR AS _fichero_origen, _ingestado_en::DATE AS _ingestado_en
        FROM tablas_mensuales ORDER BY tramite, anio, mes, columna
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze.dgt_series_historicas AS
        SELECT tramite::VARCHAR AS tramite, anio::SMALLINT AS anio, columna::VARCHAR AS columna,
               valor::BIGINT AS valor,
               _fichero_origen::VARCHAR AS _fichero_origen, _ingestado_en::DATE AS _ingestado_en
        FROM series ORDER BY tramite, anio, columna
        """
    )
    filas = _registrar(con, "bronze.dgt_tablas_mensuales", "dgt_tablas")
    return filas + _registrar(con, "bronze.dgt_series_historicas", "dgt_tablas")


# --- Eurostat -------------------------------------------------------------------------------


def ultima_ingesta(carpeta: Path) -> Path:
    """Carpeta de la ingesta más reciente (raw/<fuente>/AAAA-MM-DD)."""
    carpetas = sorted(p for p in carpeta.iterdir() if p.is_dir() and PATRON_INGESTA.match(p.name))
    if not carpetas:
        raise FileNotFoundError(f"No hay ninguna ingesta en {carpeta}")
    return carpetas[-1]


def cargar_eurostat(con: duckdb.DuckDBPyConnection, raw: Path = RAW) -> int:
    """bronze.eurostat_series: una fila por serie y mes de la última ingesta."""
    carpeta = ultima_ingesta(raw / "eurostat")
    filas = []
    for fichero in sorted(carpeta.glob("*.json")):
        documento = json.loads(fichero.read_text(encoding="utf-8"))
        actualizado = documento.get("updated")
        for periodo, valor, estado in observaciones(documento):
            filas.append(
                {
                    "id_serie": fichero.stem,
                    "periodo": periodo,
                    "valor": valor,
                    "estado": estado,
                    "actualizado_en_fuente": datetime.fromisoformat(actualizado) if actualizado else None,
                    "_fichero_origen": f"eurostat/{carpeta.name}/{fichero.name}",
                }
            )
    if not filas:
        raise FileNotFoundError(f"No hay series de Eurostat en {carpeta}")
    crudo = pd.DataFrame(filas)  # noqa: F841
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze.eurostat_series AS
        SELECT id_serie::VARCHAR AS id_serie, periodo::VARCHAR AS periodo, valor::DOUBLE AS valor,
               estado::VARCHAR AS estado, actualizado_en_fuente::TIMESTAMPTZ AS actualizado_en_fuente,
               _fichero_origen::VARCHAR AS _fichero_origen, $fecha::DATE AS _ingestado_en
        FROM crudo ORDER BY id_serie, periodo
        """,
        {"fecha": carpeta.name},
    )
    return _registrar(con, "bronze.eurostat_series", f"eurostat/{carpeta.name}")


def main() -> None:
    with conectar() as con:
        for tipo in TIPOS.values():
            print(f"bronze.dgt_{tipo.nombre}: {cargar_microdatos(con, RAW, BRONZE, tipo)} filas")
        print(f"tablas de la DGT: {cargar_tablas_dgt(con)} filas")
        print(f"bronze.eurostat_series: {cargar_eurostat(con)} filas")


if __name__ == "__main__":
    main()
