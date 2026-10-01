"""Cliente de los microdatos mensuales y las tablas estadísticas de la DGT.

Microdatos (licencia CC BY 4.0): un ZIP por mes y tipo de trámite con un único fichero
de texto de ancho fijo (ver `diseno_registro`). Se publican hacia mediados del mes
siguiente en una URL estable:

    https://www.dgt.es/microdatos/salida/AAAA/M/vehiculos/<carpeta>/export_mensual_<clave>_AAAAMM.zip

Qué meses existen se lee del listado oficial de cada tipo (una página HTML de la DGT), no
se supone: así un mes que la DGT todavía no ha publicado no se confunde con un error.

El servidor de la DGT a veces deja una descarga colgada o responde 404 a un fichero que
sí está en el listado y que segundos después se descarga bien. Por eso los ficheros del
listado se reintentan también ante un 404, y cada ZIP se comprueba (que se abre, que
contiene el fichero esperado y que no está corrupto) antes de darlo por bueno.

Las descargas se guardan tal cual en la capa raw. Un mes ya descargado no se vuelve a
pedir, salvo los últimos `REVISAR_ULTIMOS` meses publicados, por si la DGT los corrige.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from coches_usados.ingest.http import TIEMPO_MAXIMO, sesion_con_reintentos

log = logging.getLogger(__name__)

BASE = "https://www.dgt.es"
LISTADOS = BASE + "/menusecundario/dgt-en-cifras/matraba-listados/{pagina}.html"
PUBLICACIONES = BASE + "/export/sites/web-DGT/.galleries/downloads/dgt-en-cifras/publicaciones"
REVISAR_ULTIMOS = 2


@dataclass(frozen=True)
class TipoTramite:
    nombre: str  # nombre en este proyecto (y carpeta de la capa raw)
    clave: str  # parte del nombre del fichero: export_mensual_<clave>_AAAAMM
    carpeta: str  # carpeta en la URL de la DGT
    pagina: str  # página del listado oficial


TIPOS: dict[str, TipoTramite] = {
    t.nombre: t
    for t in (
        TipoTramite("matriculaciones", "mat", "matriculaciones", "matriculaciones-automoviles-mensual"),
        TipoTramite("transferencias", "trf", "transferencias", "transacciones-automoviles-mensual"),
        TipoTramite("bajas", "bajas", "bajas", "bajas-automoviles-mensual"),
    )
}

# Tablas estadísticas anuales (Excel) que se usan para cuadrar los microdatos y para la
# serie histórica larga. La DGT las publica el año siguiente.
TABLAS_ANUALES: dict[str, str] = {
    "transferencias_tablas": (
        "Cambios-de-Titularidad-Tablas-estadisticas/Cambios-de-titularidad-Tablas-estadisticas-{anio}.xlsx"
    ),
    "transferencias_series": (
        "Cambios-de-Titularidad-Series-historicas/Cambios-de-titularidad-Series-historicas-{anio}.xlsx"
    ),
    "bajas_tablas": "Bajas-Tablas-estadisticas/Bajas-Tablas-estadisticas-{anio}.xlsx",
}


class FicheroNoValido(Exception):
    """La descarga no es el ZIP esperado (corrupto, vacío o con otro contenido)."""


def nombre_fichero(tipo: TipoTramite, anio: int, mes: int) -> str:
    return f"export_mensual_{tipo.clave}_{anio}{mes:02d}"


def url_mes(tipo: TipoTramite, anio: int, mes: int) -> str:
    return f"{BASE}/microdatos/salida/{anio}/{mes}/vehiculos/{tipo.carpeta}/{nombre_fichero(tipo, anio, mes)}.zip"


def meses_del_listado(html: str, tipo: TipoTramite) -> list[tuple[int, int]]:
    """Meses (año, mes) que el listado oficial enlaza para ese tipo de trámite, ordenados."""
    patron = re.compile(
        rf"microdatos/salida/(\d{{4}})/(\d{{1,2}})/vehiculos/{tipo.carpeta}/export_mensual_{tipo.clave}_(\d{{6}})\.zip"
    )
    meses = set()
    for anio, mes, aaaamm in patron.findall(html):
        if aaaamm != f"{anio}{int(mes):02d}":
            log.warning("Enlace incoherente en el listado de %s: %s/%s -> %s", tipo.nombre, anio, mes, aaaamm)
            continue
        meses.add((int(anio), int(mes)))
    return sorted(meses)


def comprobar_zip(ruta: Path, esperado: str) -> int:
    """Comprueba que el ZIP se abre, que no está corrupto y que contiene `esperado`.txt.
    Devuelve el tamaño del fichero de texto."""
    try:
        with zipfile.ZipFile(ruta) as z:
            nombres = z.namelist()
            if nombres != [f"{esperado}.txt"]:
                raise FicheroNoValido(f"{ruta.name}: contiene {nombres}, se esperaba {esperado}.txt")
            if (malo := z.testzip()) is not None:
                raise FicheroNoValido(f"{ruta.name}: {malo} está corrupto")
            tamanio = z.getinfo(f"{esperado}.txt").file_size
    except zipfile.BadZipFile as e:
        raise FicheroNoValido(f"{ruta.name}: no es un ZIP válido ({e})") from e
    if tamanio == 0:
        raise FicheroNoValido(f"{ruta.name}: el fichero de texto está vacío")
    return tamanio


def _sha256(ruta: Path) -> str:
    resumen = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


class DgtClient:
    def __init__(
        self,
        sesion: requests.Session | None = None,
        intentos: int = 6,
        espera: float = 5.0,
        dormir=time.sleep,
    ):
        self.sesion = sesion or sesion_con_reintentos()
        self.intentos = intentos
        self.espera = espera
        self._dormir = dormir

    def meses_publicados(self, tipo: TipoTramite) -> list[tuple[int, int]]:
        respuesta = self.sesion.get(LISTADOS.format(pagina=tipo.pagina), timeout=TIEMPO_MAXIMO)
        respuesta.raise_for_status()
        meses = meses_del_listado(respuesta.text, tipo)
        if not meses:
            raise ValueError(f"El listado de {tipo.nombre} no enlaza ningún fichero: ¿ha cambiado la página?")
        return meses

    def _descargar(self, url: str, destino: Path, validar) -> None:
        """Descarga `url` en `destino` con reintentos (también ante 404) y la valida con
        `validar(ruta_temporal)` antes de moverla a su sitio."""
        temporal = destino.with_name(destino.name + ".part")
        ultimo_error: Exception | None = None
        for intento in range(1, self.intentos + 1):
            try:
                with self.sesion.get(url, stream=True, timeout=TIEMPO_MAXIMO) as respuesta:
                    respuesta.raise_for_status()
                    with temporal.open("wb") as f:
                        for bloque in respuesta.iter_content(1 << 20):
                            f.write(bloque)
                validar(temporal)
                temporal.replace(destino)
                return
            except (requests.RequestException, FicheroNoValido) as e:
                ultimo_error = e
                log.warning("Intento %d/%d de %s: %s", intento, self.intentos, url, e)
                temporal.unlink(missing_ok=True)
                if intento < self.intentos:
                    self._dormir(self.espera * intento)
        raise RuntimeError(f"No se ha podido descargar {url} tras {self.intentos} intentos") from ultimo_error

    def descargar_mes(self, tipo: TipoTramite, anio: int, mes: int, carpeta: Path) -> tuple[Path, bool]:
        """Descarga un mes en `carpeta`. Si ya había una copia y la nueva es idéntica, se
        conserva la anterior (y su fecha). Devuelve la ruta y si el contenido ha cambiado."""
        nombre = nombre_fichero(tipo, anio, mes)
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{nombre}.zip"
        nuevo = carpeta / f"{nombre}.zip.nuevo"
        self._descargar(url_mes(tipo, anio, mes), nuevo, lambda ruta: comprobar_zip(ruta, nombre))
        if destino.exists() and _sha256(destino) == _sha256(nuevo):
            nuevo.unlink()
            return destino, False
        nuevo.replace(destino)
        return destino, True

    def descargar_tabla(self, clave: str, anio: int, carpeta: Path) -> Path:
        """Descarga una tabla estadística anual. Lanza RuntimeError si no se consigue: el
        servidor de la DGT no responde 404 a un fichero que no existe, sino que redirige a un
        servidor con un certificado inválido, así que «no publicada» y «caído» no se pueden
        distinguir por el error."""
        ruta = TABLAS_ANUALES[clave].format(anio=anio)
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{clave}_{anio}.xlsx"
        self._descargar(f"{PUBLICACIONES}/{ruta}", destino, _comprobar_xlsx)
        return destino


def _comprobar_xlsx(ruta: Path) -> None:
    if not zipfile.is_zipfile(ruta):  # un .xlsx es un ZIP
        raise FicheroNoValido(f"{ruta.name}: no es un fichero de Excel")


def ingerir_microdatos(
    cliente: DgtClient,
    tipo: TipoTramite,
    desde: tuple[int, int],
    carpeta: Path,
    revisar_ultimos: int = REVISAR_ULTIMOS,
) -> list[Path]:
    """Descarga los meses publicados desde `desde` que falten en `carpeta`, más los
    últimos `revisar_ultimos` publicados. Devuelve todos los ficheros del periodo."""
    publicados = [m for m in cliente.meses_publicados(tipo) if m >= desde]
    if not publicados:
        raise ValueError(f"La DGT no tiene publicado ningún mes de {tipo.nombre} desde {desde}")
    revisar = set(publicados[-revisar_ultimos:]) if revisar_ultimos else set()
    ficheros = []
    for anio, mes in publicados:
        ruta = carpeta / f"{nombre_fichero(tipo, anio, mes)}.zip"
        if (anio, mes) in revisar or not ruta.exists():
            ruta, cambiado = cliente.descargar_mes(tipo, anio, mes, carpeta)
            log.info("%s %d-%02d: %s", tipo.nombre, anio, mes, "descargado" if cambiado else "sin cambios")
        ficheros.append(ruta)
    return ficheros


def ingerir_tablas(
    cliente: DgtClient, carpeta: Path, desde: int, hasta: int, respaldo: Path | None = None
) -> list[Path]:
    """Deja en `carpeta` las tablas estadísticas anuales de `desde` a `hasta` (ambos incluidos).

    Una tabla anual ya publicada no cambia, así que las que ya están en `carpeta` no se piden de
    nuevo y, si no están, se copian de `respaldo` (copias oficiales guardadas en el repositorio:
    el servidor de la DGT responde a veces con errores 500, también desde GitHub Actions). Solo
    se descargan las que no están en ninguno de los dos sitios. La serie histórica solo se pide
    en su última edición.

    La DGT publica cada año el anterior: si la del último año aún no está (o el servidor falla),
    se avisa y se sigue con las anteriores. Un fallo en un año anterior sí es un error. Sin
    ninguna tabla no hay con qué cuadrar los microdatos y también lo es.
    """
    ficheros = []
    for anio in range(desde, hasta + 1):
        for clave in TABLAS_ANUALES:
            if clave.endswith("_series") and anio != hasta:
                continue
            nombre = f"{clave}_{anio}.xlsx"
            destino = carpeta / nombre
            if not destino.exists() and respaldo is not None and (respaldo / nombre).exists():
                carpeta.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(respaldo / nombre, destino)
            if destino.exists():
                ficheros.append(destino)
                continue
            try:
                ficheros.append(cliente.descargar_tabla(clave, anio, carpeta))
            except RuntimeError:
                if anio != hasta:
                    raise
                log.warning("La tabla %s de %d no está disponible todavía: se sigue sin ella", clave, anio)
    if not ficheros:
        raise RuntimeError("No hay ninguna tabla estadística de la DGT: no se pueden cuadrar los microdatos")
    return ficheros
