"""Orquestación con Dagster (ver docs/adr/0002-dagster-como-orquestador.md).

Cada tabla o conjunto de ficheros es un *asset* y Dagster deduce el orden por sus
dependencias:

    raw_dgt_microdatos ──► bronze/dgt_* ─────────┐
    raw_dgt_tablas ──────► bronze/dgt_tablas_* ──┼─► modelos dbt (silver, gold)
    raw_eurostat ────────► bronze/eurostat_series ┘

Los modelos de dbt se cargan desde su manifest: cada modelo y seed es un asset y cada test
de dbt es una comprobación (*asset check*), así que el linaje va de la descarga al mart
final en un solo grafo.

En local: `uv run dagster dev` (interfaz en http://localhost:3000).
Sin servidor (CI): `uv run dagster job execute -m coches_usados.definitions -j pipeline_mensual`.
"""

import os
import shutil
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import dagster as dg
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from coches_usados import bronze
from coches_usados.ingest import dgt
from coches_usados.ingest.eurostat import EurostatClient, ingerir_series, series_del_catalogo

RAIZ = Path(__file__).resolve().parents[2]
REFERENCIA_DGT = RAIZ / "datos_de_referencia" / "dgt_tablas"

# dbt lee la ruta del warehouse de COCHES_WAREHOUSE (dbt/profiles.yml) y se ejecuta con
# dbt/ como directorio de trabajo: se fija una ruta absoluta para que Python y dbt
# escriban siempre en el mismo fichero.
os.environ.setdefault("COCHES_WAREHOUSE", str(RAIZ / "data" / "warehouse.duckdb"))

# Primer mes de microdatos que se descarga (coincide con la variable inicio_ventana de dbt).
DESDE = (2024, 1)

# Segundos base entre reintentos con la DGT: su servidor da errores 500 a ráfagas, sobre todo
# desde GitHub Actions, y conviene esperar más de lo habitual antes de rendirse.
ESPERA_DGT = 20.0

DBT_PROYECTO = DbtProject(project_dir=RAIZ / "dbt", profiles_dir=RAIZ / "dbt")
DBT_PROYECTO.prepare_if_dev()
if not DBT_PROYECTO.manifest_path.exists():
    # Fuera de `dagster dev` (tests, CI) el manifest se genera con dbt parse.
    from dbt.cli.main import dbtRunner

    resultado = dbtRunner().invoke(
        ["parse", "--quiet", "--project-dir", str(DBT_PROYECTO.project_dir), "--profiles-dir", str(RAIZ / "dbt")]
    )
    if not resultado.success:
        raise RuntimeError(f"dbt parse ha fallado: {resultado.exception}")


def _ejecutable_dbt() -> str:
    """El dbt del mismo entorno que este Python, aunque el entorno no esté activado."""
    junto_a_python = shutil.which("dbt", path=str(Path(sys.executable).parent))
    return junto_a_python or "dbt"


class Rutas(dg.ConfigurableResource):
    """Dónde están las capas raw y bronze, el warehouse y el catálogo de Eurostat. Los
    tests las apuntan a directorios temporales."""

    raw: str = str(RAIZ / "data" / "raw")
    bronze: str = str(RAIZ / "data" / "bronze")
    warehouse: str = os.environ["COCHES_WAREHOUSE"]
    catalogo_eurostat: str = str(RAIZ / "dbt" / "seeds" / "series_eurostat.csv")


# --- Ingesta (raw) --------------------------------------------------------------------


@dg.asset(group_name="raw", kinds={"python"})
def raw_dgt_microdatos(rutas: Rutas) -> dg.MaterializeResult:
    """ZIP mensuales de matriculaciones, transferencias y bajas de la DGT. Los meses ya
    descargados no se piden de nuevo, salvo los dos últimos publicados."""
    cliente = dgt.DgtClient(espera=ESPERA_DGT)
    ficheros = {
        tipo.nombre: len(dgt.ingerir_microdatos(cliente, tipo, DESDE, Path(rutas.raw) / "dgt" / tipo.nombre))
        for tipo in dgt.TIPOS.values()
    }
    return dg.MaterializeResult(metadata={f"meses_{nombre}": n for nombre, n in ficheros.items()})


@dg.asset(group_name="raw", kinds={"python"})
def raw_dgt_tablas(rutas: Rutas) -> dg.MaterializeResult:
    """Tablas estadísticas anuales (Excel) de la DGT: sirven para cuadrar los microdatos. La
    DGT publica cada año el anterior, así que se piden hasta el del año pasado; las que ya
    están descargadas o guardadas en el repositorio (`datos_de_referencia/`) no se piden."""
    ficheros = dgt.ingerir_tablas(
        dgt.DgtClient(espera=ESPERA_DGT),
        Path(rutas.raw) / "dgt_tablas",
        DESDE[0],
        date.today().year - 1,
        respaldo=REFERENCIA_DGT,
    )
    return dg.MaterializeResult(metadata={"ficheros": len(ficheros)})


@dg.asset(group_name="raw", kinds={"python"})
def raw_eurostat(rutas: Rutas) -> dg.MaterializeResult:
    """Series de precios de Eurostat del catálogo (una respuesta por serie)."""
    series = series_del_catalogo(Path(rutas.catalogo_eurostat))
    ficheros = ingerir_series(EurostatClient(), series, Path(rutas.raw) / "eurostat", fecha_ingesta=date.today())
    return dg.MaterializeResult(metadata={"series": len(ficheros), "carpeta": str(ficheros[0].parent)})


# --- Bronze ---------------------------------------------------------------------------
# Las claves coinciden con las fuentes de dbt (source('bronze', ...)), así Dagster une
# el grafo de Python con el de dbt.


def _asset_microdatos(tipo: dgt.TipoTramite) -> dg.AssetsDefinition:
    @dg.asset(
        name=f"dgt_{tipo.nombre}",
        key_prefix=["bronze"],
        deps=[raw_dgt_microdatos],
        group_name="bronze",
        kinds={"duckdb"},
    )
    def _bronze(rutas: Rutas) -> dg.MaterializeResult:
        with bronze.conectar(rutas.warehouse) as con:
            filas = bronze.cargar_microdatos(con, Path(rutas.raw), Path(rutas.bronze), tipo)
        return dg.MaterializeResult(metadata={"filas": filas})

    _bronze.__doc__ = f"Microdatos de {tipo.nombre} de la DGT: un Parquet por mes y una vista en DuckDB."
    return _bronze


bronze_microdatos = [_asset_microdatos(tipo) for tipo in dgt.TIPOS.values()]


@dg.multi_asset(
    specs=[
        dg.AssetSpec(["bronze", "dgt_tablas_mensuales"], deps=[raw_dgt_tablas], group_name="bronze", kinds={"duckdb"}),
        dg.AssetSpec(["bronze", "dgt_series_historicas"], deps=[raw_dgt_tablas], group_name="bronze", kinds={"duckdb"}),
    ],
    can_subset=False,
)
def bronze_dgt_tablas(rutas: Rutas):
    """Tablas estadísticas de la DGT: por mes y tipo, y la serie histórica anual."""
    with bronze.conectar(rutas.warehouse) as con:
        bronze.cargar_tablas_dgt(con, Path(rutas.raw))
    yield dg.MaterializeResult(asset_key=["bronze", "dgt_tablas_mensuales"])
    yield dg.MaterializeResult(asset_key=["bronze", "dgt_series_historicas"])


@dg.asset(key=["bronze", "eurostat_series"], deps=[raw_eurostat], group_name="bronze", kinds={"duckdb"})
def bronze_eurostat_series(rutas: Rutas) -> dg.MaterializeResult:
    """Última ingesta de Eurostat en DuckDB, con columnas de auditoría."""
    with bronze.conectar(rutas.warehouse) as con:
        filas = bronze.cargar_eurostat(con, Path(rutas.raw))
    return dg.MaterializeResult(metadata={"filas": filas})


@dg.asset_check(asset=bronze_eurostat_series)
def eurostat_datos_recientes(rutas: Rutas) -> dg.AssetCheckResult:
    """Eurostat publica el índice de un mes hacia mediados del mes siguiente. Si el último
    dato tiene más de cuatro meses, algo ha cambiado en la fuente: se avisa sin bloquear."""
    import duckdb

    with duckdb.connect(rutas.warehouse, read_only=True) as con:
        (ultimo,) = con.execute("SELECT max(strptime(periodo, '%Y-%m')::DATE) FROM bronze.eurostat_series").fetchone()
    hoy = date.today()
    meses = (hoy.year - ultimo.year) * 12 + hoy.month - ultimo.month
    return dg.AssetCheckResult(
        passed=meses <= 4,
        severity=dg.AssetCheckSeverity.WARN,
        metadata={"ultimo_mes": ultimo.isoformat(), "meses_de_retraso": meses},
    )


# --- dbt (silver y gold) --------------------------------------------------------------


class Traductor(DagsterDbtTranslator):
    """Agrupa los assets de dbt por capa, como en el warehouse."""

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        if dbt_resource_props["resource_type"] == "seed":
            return "referencia"
        carpeta = dbt_resource_props["fqn"][1]
        return {"staging": "silver", "intermediate": "silver", "marts": "gold"}.get(carpeta)


@dbt_assets(manifest=DBT_PROYECTO.manifest_path, project=DBT_PROYECTO, dagster_dbt_translator=Traductor())
def modelos_dbt(context: dg.AssetExecutionContext, dbt: DbtCliResource):
    """Seeds, modelos y tests de dbt: cada test se registra como comprobación del asset."""
    yield from dbt.cli(["build"], context=context).stream()


# --- Trabajo y programación -----------------------------------------------------------

pipeline_mensual = dg.define_asset_job(
    "pipeline_mensual",
    selection=dg.AssetSelection.all(),
    description="Descarga de las fuentes, carga en bronze y construcción de silver y gold.",
    # En un solo proceso y en orden: DuckDB admite un único escritor sobre el fichero del
    # warehouse, y con el ejecutor por defecto las cargas de bronze se pisarían entre sí.
    executor_def=dg.in_process_executor,
)

# La DGT publica los ficheros de un mes hacia mediados del mes siguiente y Eurostat, igual:
# el día 20 ya están.
ejecucion_mensual = dg.ScheduleDefinition(
    job=pipeline_mensual,
    cron_schedule="0 7 20 * *",
    execution_timezone="Europe/Madrid",
)

defs = dg.Definitions(
    assets=[
        raw_dgt_microdatos,
        raw_dgt_tablas,
        raw_eurostat,
        *bronze_microdatos,
        bronze_dgt_tablas,
        bronze_eurostat_series,
        modelos_dbt,
    ],
    asset_checks=[eurostat_datos_recientes],
    jobs=[pipeline_mensual],
    schedules=[ejecucion_mensual],
    resources={"rutas": Rutas(), "dbt": DbtCliResource(project_dir=DBT_PROYECTO, dbt_executable=_ejecutable_dbt())},
)
