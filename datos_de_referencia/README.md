# Datos de referencia

Copias de las **tablas estadísticas anuales de la DGT** («Cambios de titularidad» y «Bajas»).
La DGT las publica una vez al año y no las cambia, así que el pipeline las usa desde aquí y
solo descarga las de los años que falten. Se guardan en el repositorio porque el servidor de
la DGT responde con errores 500 a veces, también desde GitHub Actions (ver
[ADR 0007](../docs/adr/0007-formato-de-los-ficheros-de-la-dgt.md)).

Son ficheros oficiales sin modificar, de [dgt.es](https://www.dgt.es) (licencia CC BY 4.0).
Sirven para cuadrar los microdatos mensuales (ver [ADR 0005](../docs/adr/0005-cuadre-con-las-tablas-oficiales.md)).
El nombre es `<clave>_<año>.xlsx`; para añadir un año nuevo basta con copiar el fichero descargado
con ese nombre.
