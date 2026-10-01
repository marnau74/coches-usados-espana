"""Diseño de registro de los microdatos mensuales de la DGT (MATRABA).

Los tres ficheros (matriculaciones, transferencias y bajas) comparten el mismo formato:
texto de ancho fijo, una línea de 714 caracteres por trámite, en Latin-1 y sin cabecera.
Los campos y sus longitudes salen del documento oficial «Documento de interfaz de Envío
de Datos» de la DGT (uno por tipo de fichero, con los mismos 69 campos):
https://www.dgt.es/export/sites/web-DGT/.galleries/downloads/dgt-en-cifras/matraba/TRANSFERENCIAS_MATRABA.pdf

Los nombres se pasan a snake_case sin tildes; el orden y las longitudes son los del
documento. Si la DGT cambia el formato, la longitud de las líneas deja de cuadrar y la
carga en bronze falla (no se intenta adivinar dónde empieza cada campo).
"""

from __future__ import annotations

from dataclasses import dataclass

CODIFICACION = "latin-1"


@dataclass(frozen=True)
class Campo:
    nombre: str
    inicio: int  # posición del primer carácter, empezando en 1 (como en el documento)
    longitud: int


_LONGITUDES: tuple[tuple[str, int], ...] = (
    ("fec_matricula", 8),
    ("cod_clase_mat", 1),
    ("fec_tramitacion", 8),
    ("marca_itv", 30),
    ("modelo_itv", 22),
    ("cod_procedencia_itv", 1),
    ("bastidor_itv", 21),
    ("cod_tipo", 2),
    ("cod_propulsion_itv", 1),
    ("cilindrada_itv", 5),
    ("potencia_itv", 6),
    ("tara", 6),
    ("peso_max", 6),
    ("num_plazas", 3),
    ("ind_precinto", 2),
    ("ind_embargo", 2),
    ("num_transmisiones", 2),
    ("num_titulares", 2),
    ("localidad_vehiculo", 24),
    ("cod_provincia_veh", 2),
    ("cod_provincia_mat", 2),
    ("clave_tramite", 1),
    ("fec_tramite", 8),
    ("codigo_postal", 5),
    ("fec_prim_matriculacion", 8),
    ("ind_nuevo_usado", 1),
    ("persona_fisica_juridica", 1),
    ("codigo_itv", 9),
    ("servicio", 3),
    ("cod_municipio_ine_veh", 5),
    ("municipio", 30),
    ("kw_itv", 7),
    ("num_plazas_max", 3),
    ("co2_itv", 5),
    ("renting", 1),
    ("cod_tutela", 1),
    ("cod_posesion", 1),
    ("ind_baja_def", 1),
    ("ind_baja_temp", 1),
    ("ind_sustraccion", 1),
    ("baja_telematica", 11),
    ("tipo_itv", 25),
    ("variante_itv", 25),
    ("version_itv", 35),
    ("fabricante_itv", 70),
    ("masa_orden_marcha_itv", 6),
    ("masa_maxima_tecnica_admisible_itv", 6),
    ("categoria_homologacion_europea_itv", 4),
    ("carroceria", 4),
    ("plazas_pie", 3),
    ("nivel_emisiones_euro_itv", 8),
    ("consumo_wh_km_itv", 4),
    ("clasificacion_reglamento_vehiculos_itv", 4),
    ("categoria_vehiculo_electrico", 4),
    ("autonomia_vehiculo_electrico", 6),
    ("marca_vehiculo_base", 30),
    ("fabricante_vehiculo_base", 50),
    ("tipo_vehiculo_base", 35),
    ("variante_vehiculo_base", 25),
    ("version_vehiculo_base", 35),
    ("distancia_ejes_12_itv", 4),
    ("via_anterior_itv", 4),
    ("via_posterior_itv", 4),
    ("tipo_alimentacion_itv", 1),
    ("contrasena_homologacion_itv", 25),
    ("eco_innovacion_itv", 1),
    ("reduccion_eco_itv", 4),
    ("codigo_eco_itv", 25),
    ("fec_proceso", 8),
)


def _campos() -> tuple[Campo, ...]:
    campos, inicio = [], 1
    for nombre, longitud in _LONGITUDES:
        campos.append(Campo(nombre, inicio, longitud))
        inicio += longitud
    return tuple(campos)


CAMPOS: tuple[Campo, ...] = _campos()
LONGITUD_LINEA = sum(c.longitud for c in CAMPOS)  # 714
