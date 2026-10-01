from coches_usados.ingest.diseno_registro import CAMPOS, CODIFICACION, LONGITUD_LINEA


def test_el_diseno_tiene_los_69_campos_y_714_caracteres():
    assert len(CAMPOS) == 69
    assert LONGITUD_LINEA == 714
    assert CODIFICACION == "latin-1"


def test_los_nombres_son_unicos_y_los_campos_consecutivos():
    assert len({c.nombre for c in CAMPOS}) == len(CAMPOS)
    siguiente = 1
    for campo in CAMPOS:
        assert campo.inicio == siguiente
        siguiente += campo.longitud


def test_las_posiciones_coinciden_con_el_documento_de_la_dgt():
    """Posiciones comprobadas contra los ficheros reales y el documento «Interfaz de Envío de
    Datos»: si alguien reordena los campos, esto falla antes de que los datos se desplacen."""
    posiciones = {c.nombre: (c.inicio, c.longitud) for c in CAMPOS}
    assert posiciones["fec_matricula"] == (1, 8)
    assert posiciones["marca_itv"] == (18, 30)
    assert posiciones["modelo_itv"] == (48, 22)
    assert posiciones["cod_tipo"] == (92, 2)
    assert posiciones["cod_propulsion_itv"] == (94, 1)
    assert posiciones["cod_provincia_veh"] == (153, 2)
    assert posiciones["clave_tramite"] == (157, 1)
    assert posiciones["fec_tramite"] == (158, 8)
    assert posiciones["ind_nuevo_usado"] == (179, 1)
    assert posiciones["persona_fisica_juridica"] == (180, 1)
    assert posiciones["servicio"] == (190, 3)
    assert posiciones["categoria_vehiculo_electrico"] == (454, 4)
    assert posiciones["fec_proceso"] == (707, 8)
