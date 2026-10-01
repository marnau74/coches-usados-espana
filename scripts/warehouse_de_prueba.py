"""Construye un warehouse de prueba (solo bronze) con datos sintéticos, para ejecutar dbt en la
CI sin descargar los 2 GB de las fuentes reales.

Los ficheros imitan el formato de las fuentes (ver tests/sinteticos.py). Las vistas de bronze
leen los Parquet de una carpeta junto al warehouse (`<nombre>_bronze/`).

Uso: python scripts/warehouse_de_prueba.py data/warehouse_ci.duckdb
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

from tests.sinteticos import construir_raw  # noqa: E402

from coches_usados import bronze  # noqa: E402
from coches_usados.ingest.dgt import TIPOS  # noqa: E402


def construir(warehouse: Path) -> None:
    warehouse = warehouse.resolve()
    carpeta_bronze = warehouse.with_name(warehouse.stem + "_bronze")
    for viejo in (warehouse, warehouse.with_name(warehouse.name + ".wal")):
        viejo.unlink(missing_ok=True)
    shutil.rmtree(carpeta_bronze, ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp)
        construir_raw(raw, RAIZ / "dbt" / "seeds" / "series_eurostat.csv")
        with bronze.conectar(warehouse) as con:
            for tipo in TIPOS.values():
                bronze.cargar_microdatos(con, raw, carpeta_bronze, tipo)
            bronze.cargar_tablas_dgt(con, raw)
            bronze.cargar_eurostat(con, raw)


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "data" / "warehouse_ci.duckdb"
    construir(destino)
    print(f"Warehouse de prueba en {destino}")
