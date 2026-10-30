# Reproducción de los experimentos

Ejecutar exclusivamente en Google Colab. Los notebooks se entregan sin salidas ni contadores. Gurobi requiere los secretos `WLSACCESSID`, `WLSSECRET` y `LICENSEID`. Los notebooks incluyen sus fuentes y pruebas.

## Datos necesarios

Restaurar en `MyDrive/TESIS-EHBG-FACS/` el banco `banks/pilot00_280553a33c2ab594/` y la población completa `final_populations/final07_5abdec3f593b3050e3d0/`, con sus manifiestos, padres, tickets y certificados. La población se identifica por `ce05f08892e92f3cff035f887bdf4604e54f9ac124e4af9ae048eeaf2541acfe`.

Estos paquetes completos aún faltan en la entrega local. Un manifiesto no sustituye los datos. Para continuar la ejecución histórica también se requieren el protocolo, pesos, estados, actas y bundles originales de Drive.

## Desarrollo

Ejecutar los archivos de `notebooks/desarrollo/` en este orden:

1. **00**: recuperar y comprobar el banco sellado.
2. **01 → 02**: métodos exactos y metaheurísticos.
3. **03 → 04 → 05**: supervisado, POMO y HBG; usar GPU.
4. **03b**, si se repite el diagnóstico cruzado: seleccionar expresamente sus checkpoints históricos. No sustituirlos automáticamente por los últimos modelos.
5. **06**: fijar los identificadores de las corridas en la última asignación de `RUN_SELECTION` antes de consolidar.
6. **08_resultados_R**: actualizar ruta y hash del reporte de 06 en la celda de análisis; ejecutar con CPU.

Los identificadores guardados en los notebooks corresponden al estudio original. Al producir nuevas corridas, actualizar sus referencias explícitas; no seleccionar resultados por desempeño. Si se regenera el banco con 00, debe revisarse su acta y actualizarse la referencia común de los métodos: no se considera idéntico al banco sellado por compartir el nombre.

## Réplica nueva del experimento final

1. **07_auditoria_diseno**: auditar la población. `RUN_STAGE='audit'` no la genera. Para una población nueva se utiliza `build_population`; para reproducir el estudio, conservar la población sellada original.
2. **10_experimento_final**, en GPU T4: ejecutar la celda de entorno y reiniciar si se solicita. Definir `REPLICA_ID`, `DATA_ROOT`, ruta y hash de población. La salida usa otra carpeta de Drive. Activar `RUN_TRAINING=True` y mantener `OPEN_FINAL_TEST=False`; ejecutar hasta completar los seis entrenamientos y revisar el congelamiento.
3. En el mismo **10**, abrir `OPEN_FINAL_TEST=True` después del congelamiento. Conservar la ruta del reporte y el SHA-256 impresos. Una reconexión debe mantener identidad y configuración para recuperar la misma réplica.
4. **08_procesar_final10_R**, con CPU: cambiar `DRIVE_ROOT` a la carpeta de la réplica y fijar `FINAL_REPORT_RELATIVE_PATH` y `FINAL_REPORT_CHECKSUMS_SHA256` con la salida del paso anterior; ejecutar el análisis.

El 10 de réplica adapta la preparación y las rutas del ejecutor original; conserva el motor, las semillas, presupuestos, selección y análisis. Usa el entrenador original con recuperación, no el controlador histórico por bloques. Genera una identidad nueva y no garantiza resultados numéricos idénticos: influyen el entorno, los límites de tiempo y las interrupciones. Su ejecución y comprobaciones funcionales están pendientes en Colab.

## Continuar el protocolo original

Con todos los artefactos históricos restaurados, usar **10A → 10B → 08 final**. Están en `notebooks/continuacion/` y `notebooks/final/`. 10A completa la caché; 10B exige el protocolo original `final10_802d2255f89bb6ccacb6` y el entorno compatible, y avanza por épocas. Mantener cerrada la prueba durante el entrenamiento. Esta ruta recupera una ejecución existente; no inicializa una réplica nueva.

`referencia/` conserva protocolo y versiones originales. `procedencia.csv` documenta las transformaciones; `CHECKSUMS.json`, la integridad de esta entrega. Sólo se comprobó estructura, sintaxis e identidad de fuentes; no se ejecutaron experimentos.
