"""Empaqueta la capa gold como producto de datos para publicarla en una release de GitHub.

Contenido de `release/`:
  - `<tabla>.parquet`: una por tabla de gold (para pandas, Power BI, Spark...).
  - `coches_usados.duckdb`: las mismas tablas en un único fichero, esquema `gold`.
  - `contrato.json`: versión del contrato, tablas, columnas, tipos y filas. Quien consume
    los datos lo compara con lo que espera antes de usarlos.
  - `SHA256SUMS`: sumas de verificación de todos los ficheros anteriores.

Versionado del contrato (semántico): un cambio que rompe a quien consume (quitar o
renombrar una columna o tabla, cambiar un tipo) sube la versión mayor; añadir algo, la
menor. `VERSION_CONTRATO` se cambia a mano junto con el modelo.

Uso: python -m coches_usados.release
"""

import hashlib
import json
from datetime import date
from pathlib import Path

import duckdb

VERSION_CONTRATO = "1.0.0"
ESQUEMA = "gold"
WAREHOUSE = Path("data/warehouse.duckdb")
SALIDA = Path("release")
NOMBRE_DUCKDB = "coches_usados.duckdb"


def _tablas(con: duckdb.DuckDBPyConnection, catalogo: str | None = None) -> list[str]:
    """Tablas del esquema gold, en la base principal o en un catálogo adjunto."""
    filas = con.execute(
        "SELECT table_name FROM duckdb_tables() "
        "WHERE schema_name = ? AND database_name = coalesce(?, current_database()) ORDER BY table_name",
        [ESQUEMA, catalogo],
    ).fetchall()
    if not filas:
        raise ValueError(f"El warehouse no tiene tablas en el esquema {ESQUEMA}")
    return [nombre for (nombre,) in filas]


def _sha256(fichero: Path) -> str:
    resumen = hashlib.sha256()
    with fichero.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def construir_contrato(con: duckdb.DuckDBPyConnection, tablas: list[str]) -> dict:
    """Esquema de cada tabla de gold y el periodo que cubren los datos."""
    contrato_tablas = {}
    for tabla in tablas:
        columnas = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            [ESQUEMA, tabla],
        ).fetchall()
        (filas,) = con.execute(f'SELECT count(*) FROM {ESQUEMA}."{tabla}"').fetchone()
        contrato_tablas[tabla] = {
            "filas": filas,
            "columnas": [{"nombre": nombre, "tipo": tipo} for nombre, tipo in columnas],
        }

    desde, hasta = con.execute(f"SELECT min(fecha_id), max(fecha_id) FROM {ESQUEMA}.dim_fecha").fetchone()
    (provisional_desde,) = con.execute(f"SELECT min(fecha_id) FROM {ESQUEMA}.dim_fecha WHERE provisional").fetchone()
    return {
        "version_contrato": VERSION_CONTRATO,
        "generado": date.today().isoformat(),
        "periodo": {"desde": f"{desde // 100}-{desde % 100:02d}", "hasta": f"{hasta // 100}-{hasta % 100:02d}"},
        "provisional_desde": f"{provisional_desde // 100}-{provisional_desde % 100:02d}" if provisional_desde else None,
        "fuentes": ["DGT (microdatos y tablas estadísticas, CC BY 4.0)", "Eurostat (IPCA, prc_hicp_minr)"],
        "tablas": contrato_tablas,
    }


def exportar(warehouse: Path = WAREHOUSE, salida: Path = SALIDA) -> dict:
    """Exporta gold a `salida/` y devuelve el contrato. Antes borra la release anterior, pero
    solo los ficheros que genera este módulo: si `salida` apunta por error a otra carpeta, no
    se lleva por delante lo que haya en ella."""
    salida.mkdir(parents=True, exist_ok=True)
    for patron in ("*.parquet", NOMBRE_DUCKDB, f"{NOMBRE_DUCKDB}.wal", "contrato.json", "SHA256SUMS"):
        for viejo in salida.glob(patron):
            viejo.unlink()

    # Se abre el fichero de la release y se adjunta el warehouse en solo lectura: la
    # exportación no puede modificar el warehouse aunque haya un error.
    with duckdb.connect(str(salida / NOMBRE_DUCKDB)) as con:
        ruta = Path(warehouse).as_posix().replace("'", "''")  # ATTACH no admite parámetros
        con.execute(f"ATTACH '{ruta}' AS origen (READ_ONLY)")
        con.execute(f"CREATE SCHEMA {ESQUEMA}")
        for tabla in _tablas(con, catalogo="origen"):
            con.execute(f'CREATE TABLE {ESQUEMA}."{tabla}" AS SELECT * FROM origen.{ESQUEMA}."{tabla}"')
        con.execute("DETACH origen")

        tablas = _tablas(con)
        contrato = construir_contrato(con, tablas)
        for tabla in tablas:
            destino = (salida / f"{tabla}.parquet").as_posix()
            con.execute(f"COPY {ESQUEMA}.\"{tabla}\" TO '{destino}' (FORMAT parquet, COMPRESSION zstd)")

    (salida / "contrato.json").write_text(json.dumps(contrato, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generados = [salida / f"{tabla}.parquet" for tabla in tablas] + [salida / NOMBRE_DUCKDB, salida / "contrato.json"]
    sumas = [f"{_sha256(f)}  {f.name}" for f in sorted(generados)]
    (salida / "SHA256SUMS").write_text("\n".join(sumas) + "\n", encoding="utf-8")
    return contrato


def main() -> None:
    contrato = exportar()
    tablas = ", ".join(f"{t} ({d['filas']})" for t, d in contrato["tablas"].items())
    print(f"Release en {SALIDA}/ · contrato {contrato['version_contrato']} · {contrato['periodo']} · {tablas}")


if __name__ == "__main__":
    main()
