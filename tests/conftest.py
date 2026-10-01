"""Fixtures comunes: una capa raw sintética y un warehouse construido con ella (bronze + dbt).

El warehouse se fija en un directorio temporal antes de importar nada del proyecto, para que
los tests nunca toquen el warehouse real de data/.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="coches_tests_"))
os.environ["COCHES_WAREHOUSE"] = str(_TMP / "warehouse.duckdb")

RAIZ = Path(__file__).resolve().parents[1]
CATALOGO_EUROSTAT = RAIZ / "dbt" / "seeds" / "series_eurostat.csv"
HOY = date(2026, 10, 1)


def ejecutar_dbt(*args: str, warehouse: Path) -> subprocess.CompletedProcess:
    """dbt en un proceso aparte: dentro del de pytest dejaría abierta la conexión a DuckDB y
    bloquearía las demás."""
    dbt = shutil.which("dbt", path=str(Path(sys.executable).parent)) or "dbt"
    return subprocess.run(
        [dbt, *args, "--project-dir", str(RAIZ / "dbt"), "--profiles-dir", str(RAIZ / "dbt")],
        env={**os.environ, "COCHES_WAREHOUSE": str(warehouse)},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def raw_sintetico(tmp_path_factory) -> tuple[Path, dict[str, int]]:
    from tests.sinteticos import construir_raw

    raw = tmp_path_factory.mktemp("raw")
    cifras = construir_raw(raw, CATALOGO_EUROSTAT, HOY)
    return raw, cifras


@pytest.fixture(scope="session")
def warehouse_sintetico(raw_sintetico, tmp_path_factory) -> Path:
    """Warehouse con bronze cargado y todos los modelos de dbt construidos (tests incluidos)."""
    from coches_usados import bronze
    from coches_usados.ingest.dgt import TIPOS

    raw, _ = raw_sintetico
    carpeta = tmp_path_factory.mktemp("warehouse")
    warehouse = carpeta / "warehouse.duckdb"
    with bronze.conectar(warehouse) as con:
        for tipo in TIPOS.values():
            bronze.cargar_microdatos(con, raw, carpeta / "bronze", tipo)
        bronze.cargar_tablas_dgt(con, raw)
        bronze.cargar_eurostat(con, raw)
    resultado = ejecutar_dbt("build", warehouse=warehouse)
    assert resultado.returncode == 0, "dbt build ha fallado: " + resultado.stdout[-3000:]
    return warehouse
