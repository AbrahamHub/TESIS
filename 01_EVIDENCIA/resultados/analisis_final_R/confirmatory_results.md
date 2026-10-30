# Comparación confirmatoria de geometrías independientes

Release: final10_802d2255f89bb6ccacb6

Win-score: factibilidad conservadora primero; después costo conservador; ambos fallidos empatan.
Se promedian las semillas prefijadas dentro de geometría, con peso igual de los cuatro estratos.
Los IC y p-valores Hoeffding son conservadores y suponen independencia de geometrías. Holm controla los dos coprimarios.
HBG sin feromona aísla sólo la memoria de feromona EN INFERENCIA con los mismos pesos entrenados; no identifica efectos de TB/DB/replay ni ausencia de feromona durante entrenamiento.
La guardia FR registra degradación observada; no se ha fijado un margen de no inferioridad y no prueba ausencia de daño.

| Método - control | N geometrías | Efecto | IC95% | IC simultáneo | p Holm | Diferencia FR | Evidencia positiva |
|---|---:|---:|---|---|---:|---:|---|
| hbg_facs - hbg_untrained | 120 | -0.7917 | [-1.0000, -0.5437] | [-1.0000, -0.5214] | 0.00000 | -0.7743 | FALSE |
| hbg_facs - hbg_no_pheromone | 120 | 0.0000 | [-0.2480, 0.2480] | [-0.2702, 0.2702] | 1.00000 | 0.0000 | FALSE |

No significancia no demuestra equivalencia. Estos datos no identifican optimalidad estocástica, c+Q ni superioridad general.
El alcance es la población generada con condicionamiento de ventanas y reglas selladas, condicionado a modelos congelados y tres semillas de solver.
Fuentes: Hoeffding (1963), https://doi.org/10.1080/01621459.1963.10500830; R stats::p.adjust, https://search.r-project.org/R/refmans/stats/html/p.adjust.html

El release registra varios entornos de ejecución: las comparaciones temporales requieren separar resultados por hardware/runtime. Los tiempos son descriptivos del cómputo observado; no estiman una aceleración causal (speedup) del método. runtime_summary.csv y runtime_environments.json se conservan sellados en source_evidence.
