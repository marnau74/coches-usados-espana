# 0007 · Leer los ficheros de la DGT por su diseño de registro, y fallar si cambia

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Los ficheros mensuales de la DGT son texto de ancho fijo sin cabecera, en Latin-1, un trámite por
línea. Tres detalles hacen que una lectura ingenua pierda o desplace datos sin avisar:

1. **Codificación.** El fichero no es UTF-8. Leído como UTF-8 con `ignore_errors`, DuckDB descarta
   en silencio las líneas con eñes o tildes: 16.206 de las 325.283 del fichero de agosto de 2026
   (un 5 %), justo las de los municipios con eñe (A Coruña, Logroño…).
2. **Posiciones.** Los 69 campos y sus longitudes salen del documento oficial «Interfaz de Envío
   de Datos» de la DGT (el mismo para matriculaciones, transferencias y bajas). Un campo
   desplazado una posición da datos que parecen válidos.
3. **El servidor.** A veces deja una descarga colgada o responde 404 a un fichero que está en
   el listado y que segundos después se descarga bien. A un fichero que no existe no responde
   404, sino que redirige a otro servidor (`www-pro.dgt.es/error500.html`) con un certificado
   inválido: «aún no publicado» y «caído» no se distinguen por el error.

## Decisión

- El diseño de registro está en código (`ingest/diseno_registro.py`), con la longitud total
  (714) y tests con posiciones comprobadas contra los ficheros reales.
- **Todas** las líneas deben medir 714 caracteres: si una no, se rechaza el fichero entero. No se
  intenta adivinar dónde empieza cada campo.
- Se lee en Latin-1 y cada ZIP se valida (que se abre, que no está corrupto, que contiene el
  fichero esperado y que no está vacío) antes de aceptarlo.
- Los meses que existen se leen del **listado oficial** de cada tipo, no se suponen. Un listado sin
  enlaces es un error (la página ha cambiado).
- Cada descarga, y también la lectura del listado, se reintenta con espera creciente (20 s de base
  en el pipeline), incluso ante un 404 de un fichero listado: el servidor da errores 500 a
  ráfagas, sobre todo desde GitHub Actions. Si falla la revisión de un mes que ya se tenía, se
  conserva la copia; si falla uno que no se tenía, se detiene. La caché de la publicación se guarda
  aunque el trabajo falle, para que cada intento aproveche lo ya descargado.
- Las **tablas anuales**, que no cambian una vez publicadas, no se descargan en cada ejecución:
  las de los años ya conocidos están guardadas en `datos_de_referencia/` (ficheros oficiales sin
  modificar) y solo se descargan las de años nuevos. Hubo que hacerlo así porque el servidor de la
  DGT respondió con errores 500 persistentes a esas tablas desde GitHub Actions, mientras servía
  bien los microdatos. Si las del último año aún no están, se avisa y se sigue con las anteriores;
  un fallo en un año anterior sí detiene la ejecución.
- Los dos últimos meses publicados se vuelven a descargar en cada ejecución, por si la DGT los
  corrige; si no han cambiado, se conserva la copia (y bronze no los rehace).

## Consecuencias

- Un cambio de formato de la DGT para la publicación mensual en lugar de producir cifras falsas.
- Los ficheros diarios de matriculaciones llevan una cabecera que el mensual no tiene; se ignora
  si aparece.
