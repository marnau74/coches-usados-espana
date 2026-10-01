"""Indicadores del informe, calculados desde la capa gold del warehouse.

Cada función devuelve listas de diccionarios (JSON) para que la plantilla dibuje y redacte:
ninguna cifra del informe está escrita a mano. Las unidades son trámites de turismos (un
trámite no es un coche distinto; ver docs/adr/0004-semantica-de-los-datos.md).
"""

from __future__ import annotations

import duckdb

ELECTRIFICADOS = "('hibrido', 'hibrido_enchufable', 'electrico')"


def _filas(con: duckdb.DuckDBPyConnection, sql: str, parametros: list | None = None) -> list[dict]:
    cursor = con.execute(sql, parametros or [])
    columnas = [c[0] for c in cursor.description]
    return [dict(zip(columnas, fila, strict=True)) for fila in cursor.fetchall()]


def meta(con: duckdb.DuckDBPyConnection) -> dict:
    meses = _filas(con, "SELECT mes, anio, provisional FROM gold.dim_fecha ORDER BY mes")
    completos = [
        anio
        for anio in sorted({m["anio"] for m in meses})
        if sum(1 for m in meses if m["anio"] == anio and not m["provisional"]) == 12
    ]
    provisionales = [m["mes"] for m in meses if m["provisional"]]
    (ultimo_eurostat,) = con.execute(
        "SELECT max(strptime(periodo, '%Y-%m')::DATE) FROM bronze.eurostat_series"
    ).fetchone()
    return {
        "primer_mes": meses[0]["mes"].strftime("%Y-%m"),
        "ultimo_mes": meses[-1]["mes"].strftime("%Y-%m"),
        "provisional_desde": min(provisionales).strftime("%Y-%m") if provisionales else None,
        "anios_completos": completos,
        "ultimo_mes_eurostat": ultimo_eurostat.strftime("%Y-%m"),
    }


def serie_mensual(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Trámites de turismos por mes y tipo de trámite (las bajas, aparte)."""
    return _filas(
        con,
        """
        SELECT strftime(f.mes, '%Y-%m-%d') AS fecha, t.tramite, sum(t.tramites)::INTEGER AS tramites, f.provisional
        FROM gold.fct_tramites_mensual AS t
        JOIN gold.dim_fecha AS f USING (fecha_id)
        GROUP BY f.mes, t.tramite, f.provisional
        ORDER BY f.mes, t.tramite
        """,
    )


def combustible_mensual(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Trámites por mes, trámite (matriculación o transferencia) y combustible."""
    return _filas(
        con,
        """
        SELECT strftime(f.mes, '%Y-%m-%d') AS fecha, t.tramite, t.combustible_id AS combustible, sum(t.tramites)::INTEGER AS tramites
        FROM gold.fct_tramites_mensual AS t
        JOIN gold.dim_fecha AS f USING (fecha_id)
        WHERE t.tramite IN ('matriculacion', 'transferencia')
        GROUP BY f.mes, t.tramite, t.combustible_id
        ORDER BY f.mes, t.tramite, t.combustible_id
        """,
    )


def antiguedad_anual(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Cambios de titularidad por año y tramo de antigüedad del coche, y su antigüedad media."""
    return _filas(
        con,
        """
        SELECT f.anio, t.tramo_antiguedad AS tramo, sum(t.tramites)::INTEGER AS tramites
        FROM gold.fct_tramites_mensual AS t
        JOIN gold.dim_fecha AS f USING (fecha_id)
        WHERE t.tramite = 'transferencia'
        GROUP BY f.anio, t.tramo_antiguedad
        ORDER BY f.anio, t.tramo_antiguedad
        """,
    )


def antiguedad_media_mensual(con: duckdb.DuckDBPyConnection) -> list[dict]:
    return _filas(
        con,
        """
        SELECT strftime(f.mes, '%Y-%m-%d') AS fecha, t.tramite,
               round(sum(t.suma_antiguedad_anios) * 1.0 / sum(t.tramites_con_antiguedad), 2) AS antiguedad_media
        FROM gold.fct_tramites_mensual AS t
        JOIN gold.dim_fecha AS f USING (fecha_id)
        WHERE t.tramite IN ('matriculacion', 'transferencia')
        GROUP BY f.mes, t.tramite
        ORDER BY f.mes, t.tramite
        """,
    )


def modelos_top(con: duckdb.DuckDBPyConnection, anio: int, cuantos: int = 12) -> list[dict]:
    """Modelos con más cambios de titularidad en un año, con la antigüedad media de sus coches."""
    return _filas(
        con,
        """
        SELECT m.marca, m.modelo, sum(m.tramites)::INTEGER AS tramites,
               round(sum(m.suma_antiguedad_anios) * 1.0 / sum(m.tramites_con_antiguedad), 1) AS antiguedad_media
        FROM gold.fct_modelos_mensual AS m
        JOIN gold.dim_fecha AS f USING (fecha_id)
        WHERE m.tramite = 'transferencia' AND f.anio = ? AND m.modelo <> 'OTROS' AND m.modelo <> 'SIN MODELO'
        GROUP BY m.marca, m.modelo
        ORDER BY tramites DESC
        LIMIT ?
        """,
        [anio, cuantos],
    )


def marcas_top(con: duckdb.DuckDBPyConnection, anio: int, cuantos: int = 8) -> list[dict]:
    return _filas(
        con,
        """
        SELECT m.marca, sum(m.tramites)::INTEGER AS tramites
        FROM gold.fct_modelos_mensual AS m
        JOIN gold.dim_fecha AS f USING (fecha_id)
        WHERE m.tramite = 'transferencia' AND f.anio = ?
        GROUP BY m.marca
        ORDER BY tramites DESC
        LIMIT ?
        """,
        [anio, cuantos],
    )


def provincias(con: duckdb.DuckDBPyConnection, anio: int, cuantas: int = 10) -> list[dict]:
    """Provincias con más cambios de titularidad en un año (más Murcia, aunque no esté), con
    la antigüedad media y la parte de coches electrificados y diésel."""
    return _filas(
        con,
        f"""
        WITH por_provincia AS (
            SELECT p.provincia_id, p.provincia, sum(t.tramites) AS tramites,
                   round(sum(t.suma_antiguedad_anios) * 1.0 / sum(t.tramites_con_antiguedad), 1) AS antiguedad_media,
                   round(100.0 * sum(t.tramites) FILTER (WHERE t.combustible_id IN {ELECTRIFICADOS}) / sum(t.tramites), 1) AS pct_electrificados,
                   round(100.0 * sum(t.tramites) FILTER (WHERE t.combustible_id = 'diesel') / sum(t.tramites), 1) AS pct_diesel,
                   rank() OVER (ORDER BY sum(t.tramites) DESC) AS puesto
            FROM gold.fct_tramites_mensual AS t
            JOIN gold.dim_fecha AS f USING (fecha_id)
            JOIN gold.dim_provincia AS p USING (provincia_id)
            WHERE t.tramite = 'transferencia' AND f.anio = ? AND p.codigo_ine IS NOT NULL
            GROUP BY p.provincia_id, p.provincia
        )
        SELECT provincia_id, provincia, tramites::INTEGER AS tramites, antiguedad_media, pct_electrificados, pct_diesel, puesto::INTEGER AS puesto
        FROM por_provincia
        WHERE puesto <= ? OR provincia_id = 'MU'
        ORDER BY puesto
        """,
        [anio, cuantas],
    )


def bajas_mensual(con: duckdb.DuckDBPyConnection) -> list[dict]:
    return _filas(
        con,
        """
        SELECT strftime(f.mes, '%Y-%m-%d') AS fecha, t.motivo_baja AS motivo, sum(t.tramites)::INTEGER AS tramites
        FROM gold.fct_tramites_mensual AS t
        JOIN gold.dim_fecha AS f USING (fecha_id)
        WHERE t.tramite = 'baja'
        GROUP BY f.mes, t.motivo_baja
        ORDER BY f.mes, t.motivo_baja
        """,
    )


def precios(con: duckdb.DuckDBPyConnection) -> list[dict]:
    return _filas(
        con,
        """
        SELECT strftime(strptime(p.fecha_id::VARCHAR, '%Y%m'), '%Y-%m-%d') AS fecha, p.territorio, p.producto, p.indice, p.variacion_anual
        FROM gold.fct_precios_indice_mensual AS p
        WHERE strptime(p.fecha_id::VARCHAR, '%Y%m') >= DATE '2015-01-01'
        ORDER BY p.fecha_id, p.territorio, p.producto
        """,
    )


def historico(con: duckdb.DuckDBPyConnection) -> list[dict]:
    return _filas(
        con,
        """
        SELECT anio, grupo_vehiculo AS grupo, cambios_titularidad AS valor
        FROM gold.fct_titularidad_anual
        WHERE grupo_vehiculo IN ('turismos', 'motocicletas', 'camiones_y_furgonetas')
        ORDER BY anio, grupo_vehiculo
        """,
    )


def cuadre(con: duckdb.DuckDBPyConnection) -> dict:
    """Resultado del cuadre de los microdatos con las tablas oficiales de la DGT (el mismo
    cálculo que los tests assert_transferencias_cuadran_con_dgt y assert_bajas_cuadran_con_dgt)."""
    transferencias = _filas(
        con,
        """
        WITH micro AS (
            SELECT date_trunc('month', t.fecha_tramite)::DATE AS mes, count(*) AS n
            FROM silver.stg_dgt__transferencias AS t
            JOIN ref.tipos_vehiculo AS v ON t.cod_tipo = v.cod_tipo
            WHERE t.clave_tramite = '2' AND v.grupo = 'turismos'
            GROUP BY ALL
        )
        SELECT o.mes, o.valor AS oficial, m.n AS microdatos
        FROM silver.stg_dgt__tablas_mensuales AS o
        JOIN micro AS m ON o.mes = m.mes
        WHERE o.tramite = 'transferencias' AND o.grupo_vehiculo = 'turismos' AND NOT o.es_total
        """,
    )
    bajas = _filas(
        con,
        """
        WITH micro AS (
            SELECT date_trunc('month', fecha_tramite)::DATE AS mes, count(*) AS n
            FROM silver.stg_dgt__bajas
            WHERE cod_tipo = '40' AND clave_tramite IN ('3', '4', '7')
            GROUP BY ALL
        )
        SELECT o.mes, o.valor AS oficial, m.n AS microdatos, strftime(o.mes, '%Y-%m') AS mes_texto,
               strftime(o.mes, '%Y-%m') IN (SELECT mes FROM ref.excepciones_cuadre WHERE prueba = 'bajas_turismos') AS excepcion
        FROM silver.stg_dgt__tablas_mensuales AS o
        JOIN micro AS m ON o.mes = m.mes
        WHERE o.tramite = 'bajas' AND o.grupo_vehiculo = 'turismos' AND NOT o.es_total
        ORDER BY o.mes
        """,
    )

    def dif(filas: list[dict]) -> list[float]:
        return [abs(f["microdatos"] - f["oficial"]) * 100.0 / f["oficial"] for f in filas]

    bajas_sin_excepcion = [f for f in bajas if not f["excepcion"]]
    return {
        "meses_transferencias": len(transferencias),
        "dif_max_transferencias": round(max(dif(transferencias)), 2),
        "dif_media_transferencias": round(sum(dif(transferencias)) / len(transferencias), 2),
        "meses_bajas": len(bajas),
        "dif_max_bajas": round(max(dif(bajas_sin_excepcion)), 2),
        "excepciones_bajas": [
            {"mes": f["mes_texto"], "dif": round((f["microdatos"] - f["oficial"]) * 100.0 / f["oficial"], 1)}
            for f in bajas
            if f["excepcion"]
        ],
        "primer_mes": min(f["mes"] for f in transferencias).strftime("%Y-%m"),
        "ultimo_mes": max(f["mes"] for f in transferencias).strftime("%Y-%m"),
    }


def tardios(con: duckdb.DuckDBPyConnection) -> dict:
    """Cuántos trámites llegan tarde: en un fichero posterior al mes de su fecha. Es lo que
    hace provisionales los dos últimos meses."""
    (porcentaje_mes_anterior,) = con.execute(
        """
        SELECT round(100.0 * count(*) FILTER (WHERE date_diff('month', date_trunc('month', fecha_tramite), mes_fichero) >= 1) / count(*), 1)
        FROM silver.int_dgt__turismos
        WHERE tramite = 'transferencia'
          AND mes_fichero <= (SELECT max(mes) - interval 2 month FROM gold.dim_fecha)
        """
    ).fetchone()
    return {"pct_transferencias_en_fichero_posterior": porcentaje_mes_anterior}


def calcular(con: duckdb.DuckDBPyConnection) -> dict:
    datos_meta = meta(con)
    # Las tablas por año usan el último año completo; con menos de un año de datos, el último año.
    anio = datos_meta["anios_completos"][-1] if datos_meta["anios_completos"] else int(datos_meta["ultimo_mes"][:4])
    return {
        "meta": datos_meta,
        "serie": serie_mensual(con),
        "combustible": combustible_mensual(con),
        "antiguedad_anual": antiguedad_anual(con),
        "antiguedad_media": antiguedad_media_mensual(con),
        "modelos": modelos_top(con, anio),
        "marcas": marcas_top(con, anio),
        "provincias": provincias(con, anio),
        "bajas": bajas_mensual(con),
        "precios": precios(con),
        "historico": historico(con),
        "cuadre": cuadre(con),
        "tardios": tardios(con),
    }
