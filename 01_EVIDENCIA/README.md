# Evidencia de ejecución

Los notebooks conservan las celdas, salidas y metadatos originales. `notebooks/` reúne desarrollo, población, preparación, entrenamiento, prueba final, análisis en R y sesiones históricas. Los duplicados exactos se conservan una sola vez; `procedencia.csv` indica el origen de cada copia.

`resultados/` contiene el reporte final en R, historiales y resúmenes de los seis entrenamientos, la enmienda T4 y las extracciones guardadas de 08. `manifiestos/` conserva sus registros de procedencia. `antecedentes_locales/` contiene registros antiguos identificados como locales; no corresponden al experimento final en Colab.

No es necesario ejecutar estos archivos para consultar la evidencia. El cierre final está en `notebooks/02_experimento_final/10B_continuar_T4_cu128.ipynb` y su análisis en `08_procesar_final10_R.ipynb`.

Falta incorporar desde Drive la población completa, los paquetes completos de entrenamiento y los resultados por escenario. El reporte R está completo. Los 17 faltantes identificados en los manifiestos parciales de entrenamiento se enumeran en `faltantes.csv`; no representan todos los archivos pendientes de Drive.

`CHECKSUMS.json` registra los hashes de esta entrega. Los manifiestos originales dentro de los paquetes permanecen intactos.
