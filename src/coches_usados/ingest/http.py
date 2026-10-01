"""Sesión HTTP común a los clientes de las fuentes.

Reintenta los errores transitorios (conexión cortada, 429 y 5xx) con espera
exponencial: una fuente pública puede fallar de forma puntual y eso no debe tumbar la
ejecución mensual entera.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "coches-usados-espana (+https://github.com/marnau74/coches-usados-espana)"
# (conexión, lectura) en segundos: un fichero de la DGT de 40 MB tarda unos segundos, pero
# su servidor a veces deja la conexión colgada.
TIEMPO_MAXIMO = (15, 120)


def sesion_con_reintentos(reintentos: int = 5, espera: float = 1.0) -> requests.Session:
    """Sesión con reintentos para GET: esperas de 0, 2, 4, 8 y 16 s con los valores por defecto."""
    politica = Retry(
        total=reintentos,
        backoff_factor=espera,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        respect_retry_after_header=True,
    )
    sesion = requests.Session()
    adaptador = HTTPAdapter(max_retries=politica)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    sesion.headers["User-Agent"] = USER_AGENT
    return sesion
