# Confirmación 08 sobre exporte final10 íntegro; ejecución sólo en Colab.
args <- commandArgs(trailingOnly = TRUE)
if (Sys.getenv("SVRPLAB_COLAB_ANALYSIS") != "1" || length(args) != 2L ||
    !file.exists("/content/.svrplab_final08_verified")) stop("Usar notebook 08 en Colab con verificación final10.")
input <- normalizePath(args[[1]], mustWork = TRUE); output <- args[[2]]
if (dir.exists(output)) stop("No sobrescribir evidencia de análisis.")
dir.create(output, recursive = TRUE)
options(stringsAsFactors = FALSE, warn = 2, OutDec = "."); Sys.setenv(TZ = "UTC")
read <- function(name) read.csv(file.path(input, name), colClasses = "character", check.names = FALSE,
                               na.strings = "", fileEncoding = "UTF-8")
write <- function(x, name) write.csv(x, file.path(output, name), row.names = FALSE, na = "", fileEncoding = "UTF-8")
need <- function(x, fields) if (!all(fields %in% names(x))) stop(paste("Columnas faltantes:", paste(setdiff(fields, names(x)), collapse = ",")))
num <- function(x) {
  value <- suppressWarnings(as.numeric(x))
  if (any(!is.na(x) & !is.finite(value))) stop("Métrica no finita.")
  value
}
truth <- function(x) {
  if (any(!is.na(x) & !x %in% c("True", "False", "true", "false"))) stop("Booleano inválido.")
  !is.na(x) & x %in% c("True", "true")
}
key <- function(x, fields) do.call(paste, c(x[fields], sep = "|"))
mean_available <- function(x) if (all(is.na(x))) NA_real_ else mean(x[!is.na(x)])
bridge <- read("analysis_bridge.csv"); meta <- setNames(bridge$value, bridge$key)
if (meta[["schema_version"]] != "final-analysis-export-v1" || meta[["role"]] != "confirmatory_holdout" ||
    meta[["analysis_mode"]] != "confirmatory" || meta[["primary_inference"]] != "stratified_geometry_weighted_hoeffding_mean_bound") stop("Contrato final distinto del análisis preespecificado.")
methods <- read("expected_methods.csv")$method; seeds <- read("expected_seeds.csv")$solver_seed
policies <- read("expected_policies.csv")$policy; sizes <- read("expected_sizes.csv")$n_customers
contrasts <- read("primary_contrasts.csv")
if (nrow(contrasts) != 2L || !identical(contrasts$method, c("hbg_facs", "hbg_facs")) ||
    !setequal(contrasts$reference_method, c("hbg_untrained", "hbg_no_pheromone"))) stop("Familia coprimaria alterada.")
alpha <- num(meta[["familywise_alpha"]]); tie_abs <- num(meta[["cost_tie_absolute_minutes"]]); tie_rel <- num(meta[["cost_tie_relative"]])
if (!identical(alpha, .05) || tie_abs < 0 || tie_rel < 0) stop("Parámetros estadísticos inválidos.")
hashes <- read("input_file_hashes.csv")
verify <- function() {
  for (i in seq_len(nrow(hashes))) {
    actual <- system2("sha256sum", shQuote(file.path(input, hashes$relative_path[[i]])), stdout = TRUE)
    if (length(actual) != 1L || substr(actual, 1, 64) != hashes$sha256[[i]]) stop("Fuente final cambió.")
  }
}
verify()
registry <- read("registry.csv")
need(registry, c("instance_sha256", "geometry_group_sha256", "n_customers"))
if (anyNA(registry[c("instance_sha256", "geometry_group_sha256", "n_customers")]) || anyDuplicated(registry$instance_sha256) || anyDuplicated(registry$geometry_group_sha256)) stop("Test debe contener una instancia por geometría independiente.")
if (!setequal(registry$n_customers, sizes)) stop("Estratos de tamaños incompletos.")
quota <- num(meta[["test_geometries_per_size"]])
if (any(table(factor(registry$n_customers, levels = sizes)) != quota)) stop("Cuota final diferente del sello.")
attempts <- read("attempts.csv")
keys <- c("instance_sha256", "policy", "method", "solver_seed")
need(attempts, c(keys, "geometry_group_sha256", "n_customers", "evaluation_status", "solver_status",
  "structural_valid", "conservative_feasible", "search_objective_minutes", "scenario_strict_feasibility",
  "mean_travel_minutes", "cvar_travel_minutes", "mean_waiting_minutes", "mean_recourse_reorders", "search_total_seconds",
  "artifact_status", "scenario_success_per_scheduled_attempt"))
# Ausencia de un indicador de validez es un error de datos, nunca FALSE.
required_status <- c("artifact_status", "solver_status", "evaluation_status", "structural_valid", "conservative_feasible")
if (anyNA(attempts[required_status]) || any(attempts$artifact_status != "observed")) stop("Artefacto/estado/flags ausentes o no observados: detener análisis.")
if (any(!attempts$evaluation_status %in% c("validated", "no_solution"))) stop("Estado de evaluación no admitido.")
structural <- truth(attempts$structural_valid)
conservative <- truth(attempts$conservative_feasible)
evaluated <- attempts$evaluation_status == "validated"
if (any(conservative & !structural) || any(evaluated & !structural) || any(!evaluated & structural)) stop("Incoherencia entre evaluación, estructura y factibilidad conservadora.")
if (any(attempts$solver_status %in% c("solver_error", "evaluation_error", "environment_error", "license_pending", "not_available", "unavailable"))) stop("Error técnico/disponibilidad: no convertir en fallo estadístico del método.")
expected <- expand.grid(instance_sha256 = registry$instance_sha256, policy = policies,
                        method = methods, solver_seed = seeds, stringsAsFactors = FALSE)
if (anyNA(attempts[keys]) || anyDuplicated(key(attempts, keys)) ||
    !setequal(key(attempts, keys), key(expected, keys))) stop("Faltan/sobran artefactos: no recodificar como fallo.")
reg <- registry[match(attempts$instance_sha256, registry$instance_sha256), ]
for (field in c("geometry_group_sha256", "n_customers")) if (any(attempts[[field]] != reg[[field]])) stop("Identidad final alterada.")
for (field in c("search_objective_minutes", "scenario_strict_feasibility", "mean_travel_minutes", "cvar_travel_minutes",
                "mean_waiting_minutes", "mean_recourse_reorders", "search_total_seconds", "scenario_success_per_scheduled_attempt")) attempts[[field]] <- num(attempts[[field]])
if (any(evaluated & is.na(attempts$scenario_strict_feasibility)) ||
    any(!evaluated & (!is.na(attempts$scenario_strict_feasibility) | !is.na(attempts$search_objective_minutes))) ||
    anyNA(attempts$scenario_success_per_scheduled_attempt)) stop("Estado de evaluación incompatible con mediciones registradas.")
expected_success <- ifelse(evaluated, attempts$scenario_strict_feasibility, 0)
if (any(abs(attempts$scenario_success_per_scheduled_attempt - expected_success) > 1e-12)) stop("Éxito end-to-end incompatible con evaluación/no_solution.")
attempts$evaluated <- evaluated
attempts$valid <- evaluated & structural & conservative
if (any(attempts$valid & (is.na(attempts$search_objective_minutes) | attempts$search_objective_minutes < 0))) stop("Plan válido sin objetivo conservador.")
attempts$success <- ifelse(attempts$evaluated, attempts$scenario_strict_feasibility, NA_real_)
no_solution <- !is.na(attempts$evaluation_status) & attempts$evaluation_status == "no_solution" &
  !is.na(attempts$structural_valid) & !truth(attempts$structural_valid) &
  !is.na(attempts$solver_status) & attempts$solver_status != "license_pending"
attempts$success[no_solution] <- 0
if (any(attempts$success < 0 | attempts$success > 1, na.rm = TRUE)) stop("FR fuera de [0,1].")
# Filas secundarias/controles incompletas siguen visibles; coprimarios requieren datos íntegros.
write(attempts, "attempt_panel_final.csv")
primary <- attempts[attempts$policy == meta[["primary_policy"]], ]
geometry_scores <- list(); paired_seeds <- list()
for (i in seq_len(nrow(contrasts))) {
  method <- contrasts$method[[i]]; reference <- contrasts$reference_method[[i]]
  a <- primary[primary$method == method, ]; b <- primary[primary$method == reference, ]
  pairing <- c("instance_sha256", "solver_seed")
  b <- b[match(key(a, pairing), key(b, pairing)), ]
  if (nrow(a) != nrow(registry) * length(seeds) || anyNA(b$method) || anyNA(a$success) || anyNA(b$success)) stop("Coprimario incompleto: detener inferencia.")
  score <- as.numeric(a$valid) - as.numeric(b$valid)
  both <- a$valid & b$valid
  tolerance <- pmax(tie_abs, tie_rel * pmax(abs(a$search_objective_minutes), abs(b$search_objective_minutes)))
  difference <- b$search_objective_minutes - a$search_objective_minutes
  score[both] <- ifelse(abs(difference[both]) <= tolerance[both], 0, sign(difference[both]))
  # Una comparación emparejada es un estimando operacional con semillas fijas,
  # no supone que los RNG de métodos distintos generen trayectorias equivalentes.
  paired <- data.frame(a[c("instance_sha256", "geometry_group_sha256", "n_customers", "solver_seed")],
    method = method, reference_method = reference, win_score = score,
    method_valid = a$valid, reference_valid = b$valid,
    method_success = a$success, reference_success = b$success, fr_difference = a$success - b$success)
  paired_seeds[[i]] <- paired
  geometry_scores[[i]] <- do.call(rbind, lapply(split(seq_len(nrow(paired)), paired$geometry_group_sha256), function(ii) {
    x <- paired[ii, ]
    if (nrow(x) != length(seeds) || !setequal(x$solver_seed, seeds)) stop("Semillas prefijadas incompletas.")
    data.frame(x[1, c("geometry_group_sha256", "n_customers", "method", "reference_method")],
      win_score = mean(x$win_score), fr_difference = mean(x$fr_difference),
      method_valid_fraction = mean(x$method_valid), reference_valid_fraction = mean(x$reference_valid),
      expected_seeds = length(seeds), independent_geometry_count = 1L)
  }))
}
paired <- do.call(rbind, paired_seeds); geometry <- do.call(rbind, geometry_scores)
write(paired, "seed_pair_scores.csv"); write(geometry, "geometry_primary_scores.csv")
# Hoeffding para X_g en [-1,1] y pesos fijados por estrato: sum(w_g)=1.
# p <= 2 exp(-estimate^2/(2 sum(w_g^2))); intervalos conservadores sin simetría.
results <- do.call(rbind, lapply(seq_len(nrow(contrasts)), function(i) {
  x <- geometry[geometry$method == contrasts$method[[i]] & geometry$reference_method == contrasts$reference_method[[i]], ]
  counts <- table(factor(x$n_customers, levels = sizes))
  if (any(counts != quota)) stop("Contraste no cubre todo el test.")
  weights <- 1 / (length(sizes) * as.numeric(counts[match(x$n_customers, names(counts))]))
  estimate <- sum(weights * x$win_score); square_sum <- sum(weights^2)
  radius <- sqrt(2 * square_sum * log(2 / alpha))
  simultaneous <- sqrt(2 * square_sum * log(2 * nrow(contrasts) / alpha))
  fr_delta <- sum(weights * x$fr_difference)
  data.frame(method = contrasts$method[[i]], reference_method = contrasts$reference_method[[i]],
    geometry_count = nrow(x), estimate = estimate, ci95_lower = max(-1, estimate - radius),
    ci95_upper = min(1, estimate + radius), simultaneous_ci_lower = max(-1, estimate - simultaneous),
    simultaneous_ci_upper = min(1, estimate + simultaneous),
    p_two_sided = min(1, 2 * exp(-estimate^2 / (2 * square_sum))),
    fr_difference = fr_delta, fr_ci95_lower = max(-1, fr_delta - radius), fr_ci95_upper = min(1, fr_delta + radius),
    fr_guardrail = if (fr_delta < 0) "observed_degradation_report_explicitly" else "no_observed_degradation_not_noninferiority_proof",
    scope = "geometry_population_conditional_on_frozen_models_and_finite_seed_set",
    inference = "stratified_geometry_weighted_hoeffding_mean_bound", sum_squared_geometry_weights = square_sum,
    minimum_abs_score_for_first_holm_rejection = simultaneous,
    primary_evidence_is_not_global_robustness = TRUE)
}))
results$p_holm <- p.adjust(results$p_two_sided, method = "holm", n = 2L)
results$holm_reject <- results$p_holm <= alpha
results$positive_primary_evidence <- results$holm_reject & results$estimate > 0
results$negative_primary_evidence <- results$holm_reject & results$estimate < 0
write(results, "coprimary_inference.csv")
# Secundarios descriptivos; no se ensaya una batería post hoc de p-valores.
secondary <- do.call(rbind, lapply(split(seq_len(nrow(attempts)), key(attempts, c("instance_sha256", "policy", "method"))), function(ii) {
  x <- attempts[ii, ]; valid <- x$valid; known <- sum(!is.na(x$success)); expected <- nrow(x)
  data.frame(x[1, c("instance_sha256", "geometry_group_sha256", "n_customers", "policy", "method")],
    expected = expected, evaluated = sum(x$evaluated), conservative_valid = sum(valid), known_success = known,
    success = if (known == expected) mean(x$success) else NA_real_,
    success_lower = sum(x$success, na.rm = TRUE) / expected,
    success_upper = (sum(x$success, na.rm = TRUE) + expected - known) / expected,
    travel_conditional = mean_available(x$mean_travel_minutes[valid]),
    cvar_conditional = mean_available(x$cvar_travel_minutes[valid]),
    duration_conditional = mean_available((x$mean_travel_minutes + x$mean_waiting_minutes)[valid]),
    recourse_reorders = mean_available(x$mean_recourse_reorders[x$evaluated]),
    search_seconds = mean_available(x$search_total_seconds), independent_geometry_count = 1L)
}))
write(secondary, "secondary_descriptive_by_geometry.csv")
secondary_lines <- c("# Resultados secundarios descriptivos por tamaño", "",
  "Métodos en orden fijo. N cuenta geometrías. Costos condicionados a planes conservadores válidos; comparar con cobertura.",
  "Las cotas FR reflejan desconocimiento cuando falta medición; no son IC poblacionales.",
  "Para diferencias de costo pareadas con todas las semillas válidas en ambos métodos usar secondary_common_valid_costs.csv.", "",
  "| n | Política | Método | N | Válidos/intentos | Geometrías con viaje/N | Viaje | Duración | FR [cotas] |",
  "|---:|---|---|---:|---:|---:|---:|---:|---|")
fmt <- function(value) if (is.na(value)) "—" else sprintf("%.2f", value)
for (size in sizes) for (policy in policies) for (method in methods) {
  x <- secondary[secondary$n_customers == size & secondary$policy == policy & secondary$method == method, ]
  secondary_lines <- c(secondary_lines, sprintf("| %s | %s | %s | %d | %d/%d | %d/%d | %s | %s | [%.3f, %.3f] |",
    size, policy, method, nrow(x), sum(x$conservative_valid), sum(x$expected),
    sum(!is.na(x$travel_conditional)), nrow(x), fmt(mean_available(x$travel_conditional)),
    fmt(mean_available(x$duration_conditional)), mean(x$success_lower), mean(x$success_upper)))
}
secondary_lines <- c(secondary_lines, "", "No hay pruebas secundarias post hoc ni ranking global. Los CSV conservan CVaR, reordenamientos y tiempos.",
  "La memoria se informa sólo cuando hay medición: CUDA del proceso durante el intento y RSS máximo histórico del proceso; no son incrementos aislados por método. Entrenamiento/validación aparecen por checkpoint en offline_model_costs.csv.")
writeLines(secondary_lines, file.path(output, "secondary_results.md"), useBytes = TRUE)

# Costos offline se muestran una vez por checkpoint, incluido el rechazado; HBG
# sin feromona reutiliza esos pesos y no duplica el cargo de entrenamiento.
offline <- read("offline_model_costs.csv")
need(offline, c("method", "solver_seed", "model_checkpoint_sha256", "training_seconds_including_validation", "validation_seconds_already_included"))
if (anyDuplicated(key(offline, c("method", "solver_seed")))) stop("Costo offline duplicado por semilla/modelo.")
write(offline, "offline_model_costs.csv")
for (field in c("evaluation_seconds", "trace_validation_seconds", "peak_cuda_allocated_bytes", "process_max_rss_kib")) {
  if (!field %in% names(attempts)) attempts[[field]] <- NA_real_ else attempts[[field]] <- num(attempts[[field]])
}
search_keys <- c("instance_sha256", "method", "solver_seed")
for (ii in split(seq_len(nrow(attempts)), key(attempts, search_keys))) {
  values <- attempts$search_total_seconds[ii]
  if (length(unique(values)) != 1L) stop("Tiempo de búsqueda cambia entre políticas de un mismo intento.")
}
search_once <- attempts[!duplicated(key(attempts, search_keys)), ]
compute <- do.call(rbind, lapply(methods, function(method) {
  x <- search_once[search_once$method == method, ]; evaluations <- attempts[attempts$method == method, ]
  total_if_complete <- function(values) if (anyNA(values)) NA_real_ else sum(values)
  data.frame(method = method, search_attempts = nrow(x),
    search_seconds = total_if_complete(x$search_total_seconds),
    evaluated_policy_rows = sum(evaluations$evaluated),
    evaluation_time_rows_available = sum(!is.na(evaluations$evaluation_seconds)),
    evaluation_seconds = total_if_complete(evaluations$evaluation_seconds),
    trace_validation_time_rows_available = sum(!is.na(evaluations$trace_validation_seconds)),
    trace_validation_seconds = total_if_complete(evaluations$trace_validation_seconds),
    training_is_in_separate_shared_checkpoint_table = TRUE,
    missing_time_is_unknown_not_zero = TRUE,
    cuda_peak_rows_available = sum(!is.na(x$peak_cuda_allocated_bytes)),
    cuda_process_peak_during_attempt_bytes = if (all(is.na(x$peak_cuda_allocated_bytes))) NA_real_ else max(x$peak_cuda_allocated_bytes, na.rm = TRUE),
    cpu_lifetime_high_water_rows_available = sum(!is.na(x$process_max_rss_kib)),
    cpu_process_lifetime_high_water_kib = if (all(is.na(x$process_max_rss_kib))) NA_real_ else max(x$process_max_rss_kib, na.rm = TRUE),
    memory_scope = "process_memory_not_isolated_method_increment;_training_memory_not_measured")
}))
write(compute, "compute_costs_without_policy_search_duplication.csv")

# Costos secundarios sólo sobre la misma geometría con todas las semillas válidas
# en ambos métodos; cada exclusión conserva su fila, denominador y motivo.
cost_pairs <- unique(rbind(contrasts, data.frame(method = setdiff(methods, "gurobi"), reference_method = "gurobi")))
paired_costs <- list(); counter <- 0L
for (i in seq_len(nrow(cost_pairs))) for (policy in policies) for (geometry_id in registry$geometry_group_sha256) {
  a <- attempts[attempts$geometry_group_sha256 == geometry_id & attempts$policy == policy & attempts$method == cost_pairs$method[[i]], ]
  b <- attempts[attempts$geometry_group_sha256 == geometry_id & attempts$policy == policy & attempts$method == cost_pairs$reference_method[[i]], ]
  b <- b[match(a$solver_seed, b$solver_seed), ]
  for (metric in c("search_objective_minutes", "mean_travel_minutes", "cvar_travel_minutes", "duration_minutes")) {
    av <- if (metric == "duration_minutes") a$mean_travel_minutes + a$mean_waiting_minutes else a[[metric]]
    bv <- if (metric == "duration_minutes") b$mean_travel_minutes + b$mean_waiting_minutes else b[[metric]]
    eligible <- nrow(a) == length(seeds) && nrow(b) == length(seeds) && all(a$valid) && all(b$valid) && !anyNA(av) && !anyNA(bv)
    counter <- counter + 1L
    paired_costs[[counter]] <- data.frame(geometry_group_sha256 = geometry_id,
      n_customers = registry$n_customers[match(geometry_id, registry$geometry_group_sha256)], policy = policy,
      method = cost_pairs$method[[i]], reference_method = cost_pairs$reference_method[[i]], metric = metric,
      expected_seeds = length(seeds), method_valid = sum(a$valid), reference_valid = sum(b$valid),
      status = if (eligible) "common_complete_valid_geometry" else "excluded_incomplete_or_invalid",
      method_mean = if (eligible) mean(av) else NA_real_, reference_mean = if (eligible) mean(bv) else NA_real_,
      delta = if (eligible) mean(av) - mean(bv) else NA_real_, independent_geometry_count = 1L,
      scope = "secondary_descriptive_conditional_common_complete_valid_geometry")
  }
}
write(do.call(rbind, paired_costs), "secondary_common_valid_costs.csv")
# Cota conservadora frente a costo conservador, sin restarla al viaje estocástico.
if ("best_bound" %in% names(attempts)) {
  attempts$best_bound <- num(attempts$best_bound)
  gaps <- lapply(seq_len(nrow(attempts)), function(i) {
    x <- attempts[i, ]; exact <- attempts[attempts$instance_sha256 == x$instance_sha256 & attempts$method == "gurobi", ]
    bound <- if (all(is.na(exact$best_bound))) NA_real_ else max(exact$best_bound, na.rm = TRUE)
    objective <- if (x$valid) x$search_objective_minutes else NA_real_
    compatible <- !is.na(bound) && !is.na(objective) && objective > 0 && bound <= objective + max(tie_abs, tie_rel * abs(objective))
    data.frame(x[c("instance_sha256", "geometry_group_sha256", "n_customers", "policy", "method", "solver_seed")],
      conservative_objective_minutes = objective, gurobi_conservative_bound_minutes = bound,
      gap_upperbound_pct = if (compatible) 100 * max(0, objective - bound) / objective else NA_real_,
      status = if (compatible) "available_conservative_bound_gap" else "unavailable_zero_or_inconsistent",
      bound_envelope_is_not_single_attempt_runtime = TRUE, not_stochastic_optimality = TRUE,
      gap_denominator = "candidate_conservative_objective_not_unknown_optimum")
  })
  write(do.call(rbind, gaps), "secondary_conservative_gap_audit.csv")
}

lines <- c("# Comparación confirmatoria de geometrías independientes", "",
  paste("Release:", meta[["final_release_id"]]), "",
  "Win-score: factibilidad conservadora primero; después costo conservador; ambos fallidos empatan.",
  "Se promedian las semillas prefijadas dentro de geometría, con peso igual de los cuatro estratos.",
  "Los IC y p-valores Hoeffding son conservadores y suponen independencia de geometrías. Holm controla los dos coprimarios.",
  "HBG sin feromona aísla sólo la memoria de feromona EN INFERENCIA con los mismos pesos entrenados; no identifica efectos de TB/DB/replay ni ausencia de feromona durante entrenamiento.",
  "La guardia FR registra degradación observada; no se ha fijado un margen de no inferioridad y no prueba ausencia de daño.", "",
  "| Método - control | N geometrías | Efecto | IC95% | IC simultáneo | p Holm | Diferencia FR | Evidencia positiva |",
  "|---|---:|---:|---|---|---:|---:|---|")
for (i in seq_len(nrow(results))) {
  x <- results[i, ]
  lines <- c(lines, sprintf("| %s - %s | %d | %.4f | [%.4f, %.4f] | [%.4f, %.4f] | %.5f | %.4f | %s |",
    x$method, x$reference_method, x$geometry_count, x$estimate, x$ci95_lower, x$ci95_upper,
    x$simultaneous_ci_lower, x$simultaneous_ci_upper, x$p_holm, x$fr_difference, x$positive_primary_evidence))
}
lines <- c(lines, "", "No significancia no demuestra equivalencia. Estos datos no identifican optimalidad estocástica, c+Q ni superioridad general.",
  "El alcance es la población generada con condicionamiento de ventanas y reglas selladas, condicionado a modelos congelados y tres semillas de solver.",
  "Fuentes: Hoeffding (1963), https://doi.org/10.1080/01621459.1963.10500830; R stats::p.adjust, https://search.r-project.org/R/refmans/stats/html/p.adjust.html")
writeLines(lines, file.path(output, "confirmatory_results.md"), useBytes = TRUE)
draw <- function() {
  par(mar = c(5, 12, 4, 1), las = 1)
  y <- seq_len(nrow(results))
  plot(results$estimate, y, xlim = c(-1, 1), ylim = c(.5, nrow(results) + .5), yaxt = "n", pch = 19,
       xlab = "Win-score medio con IC simultaneo Hoeffding", ylab = "", main = "Dos contrastes coprimarios; N por geometria")
  axis(2, y, paste0(results$method, " - ", results$reference_method, " (N=", results$geometry_count, ")"), cex.axis = .7)
  segments(results$simultaneous_ci_lower, y, results$simultaneous_ci_upper, y, lwd = 2)
  abline(v = 0, lty = 2, col = "#777777")
}
pdf(file.path(output, "coprimary_effects.pdf"), width = 11, height = 5); draw(); dev.off()
png(file.path(output, "coprimary_effects.png"), width = 3300, height = 1500, res = 300); draw(); dev.off()
verify()
writeLines(capture.output(sessionInfo()), file.path(output, "sessionInfo.txt"))
write(data.frame(check = c("source_hashes_before_after", "all_scheduled_attempts_present", "complete_primary_seed_pairs",
                          "independent_geometry_quotas", "two_coprimaries_holm", "no_secondary_pvalue_search"), passed = TRUE), "processing_checks.csv")
cat("R: inferencia coprimaria completa; el notebook debe sellar el reporte.\n")
