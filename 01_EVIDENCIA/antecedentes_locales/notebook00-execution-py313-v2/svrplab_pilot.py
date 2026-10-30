"""Notebook 00: datos, auditoría, CRN y evaluación independiente del solver.

Adaptación del generador de tráfico de SVRPBench (MIT, Ahmed Heakl, 2024).
Ver docs/SVRPBench-LICENSE.txt y docs/NOTEBOOK_00.md para las diferencias.
No contiene entrenamiento HBG/AM/POMO ni demuestra superioridad estadística.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time
import urllib.request
import warnings
from contextlib import contextmanager
from dataclasses import asdict, dataclass

import numpy as np

UPSTREAM_SHA = '9fd5737ae598e1667ae94907f9c45224c501c84b'
HF_REVISION = '4a79ade38f663edaefa62e34e7c2ea330a2e15da'
ROWS_SHA = '9c055992902ddf9c6133c438bc35e09623d59b0a376b623cbadd3375bbd36147'
SOURCE_FILES = ('city.py', 'constants.py', 'common.py', 'time_windows_generator.py',
                'travel_time_generator.py', 'real_twcvrp.py')
SOURCE_HASHES = {'city.py': 'c55ef26cfbd24fa705afd6223aa45cf53094168ba02d95552562c9a66dc09e9e', 'constants.py': '28cca2aecf61bad8e4fb75dc6807f18f200998eb8a767a62e425c50641f25758', 'common.py': '8400c0e767c189987ccf26dee9688117ee2deb4e14f3c8ce516dd30e70ea5f5b', 'time_windows_generator.py': '90b19f40fdef99604345bf5935ceb40b54f10e5d869c77974bcef736a26d2afb', 'travel_time_generator.py': 'a0f6251321bcf053f251c58dd6d7ce207b7c2f66595444fdface1d54127d6e5e', 'real_twcvrp.py': '3530823c42ef6480b6d0aa63d3535b8e8313e20d82b904647653cf0c5da9de07'}
PROTOCOL_VERSION = 'pilot-00-v2'
WINDOW_POLICY = 'balanced_insertion_mean_time_projection_v1'
# Instancias validadas (master_seed, n) -> sha256. Coinciden con Python 3.12 + versiones
# fijadas y con el entorno Colab (Python 3.13, numpy 2.1.3, scikit-learn 1.6.1).
# Garantizan reproducibilidad por contenido, no por versión de biblioteca.
REFERENCE_INSTANCE_SHA = {
    (20260916, 50): '17dc741073c2b524d3bfbd97912fd4abd9ab033267faf2bc629265de9fb1f0f9',
    (20260916, 100): '540bb7187a90ef06f56f90c4a5e0cb0438bfc902d2077975fb3faa7fe914319f',
    (20260916, 200): 'fb3e12f54bd1003e00ed1910601935fe714aa561ef2feadeae90221592644445',
    (20260916, 300): '3e7cf85cf9c76b4fb10b73d013ffbc4b6ee7017d777ad1c093928be45877eec8',
}
REFERENCE_FEASIBLE_SHA = {
    50: 'cb57f1068a3c7b173dbd087154f8276a8ba98df7cb45cc542fc8a3f5ef12b94f',
    100: '3e70717e9302373d12ddf25c613ef3c84522ba6c4f8a735c3368684db60eccff',
    200: '387948482f58d7f1e8d6c109f5edcbcc59ea318660b166119e76dc5b3f6c422c',
    300: 'd2c4b2457c08cf9fa7981fa13a85bd0637ea914ef9eb281f62acdc96f3f3b231',
}


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def seed_for(*parts):
    return int.from_bytes(hashlib.sha256(canonical_bytes(parts)).digest()[:8], 'little')


@contextmanager
def legacy_seed(seed):
    """Aísla las RNG globales que usa el generador oficial."""
    py, np_state = random.getstate(), np.random.get_state()
    random.seed(seed)
    np.random.seed(seed % 2**32)
    try:
        yield
    finally:
        random.setstate(py)
        np.random.set_state(np_state)


def download(url, destination):
    """Descarga atómica, tiempo limitado; no ejecuta contenido descargado."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'SVRPLab-thesis/1.0'})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    temporary = destination.with_suffix(destination.suffix + '.download')
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return destination


def fetch_upstream(root):
    root = Path(root)
    for name in SOURCE_FILES:
        path = root / 'vrp_bench' / name
        if not path.exists():
            download(f'https://raw.githubusercontent.com/yehias21/svrpbench/{UPSTREAM_SHA}/vrp_bench/{name}', path)
    if not (root / 'LICENSE').exists():
        download(f'https://raw.githubusercontent.com/yehias21/svrpbench/{UPSTREAM_SHA}/LICENSE', root / 'LICENSE')
    for name, expected in SOURCE_HASHES.items():
        if file_hash(root / 'vrp_bench' / name) != expected:
            raise ValueError(f'Código upstream modificado: {name}')
    # Hashes verificados; el commit completo fija las URLs.
    return {str(p.relative_to(root)): file_hash(p)
            for p in sorted(root.rglob('*')) if p.is_file() and p.suffix == '.py'}


def load_catalog(cache):
    """Parquet fijado; fallback oficial Viewer sólo si coincide el hash de 560 filas.

    La revisión del Viewer no se puede seleccionar: se identifica como snapshot
    verificado por contenido, nunca como descarga de la revisión fijada.
    """
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    snapshot = cache / 'catalog_rows.json'
    meta_file = cache / 'catalog_provenance.json'
    if snapshot.exists():
        rows = json.loads(snapshot.read_text())
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {'transport': 'local_verified_snapshot'}
    else:
        rows = None
        try:
            from huggingface_hub import hf_hub_download
            import pyarrow.parquet as pq
            path = hf_hub_download(repo_id='MBZUAI/svrp-bench',
                filename='data/test-00000-of-00001.parquet', repo_type='dataset',
                revision=HF_REVISION, local_dir=str(cache / 'hf'))
            rows = pq.read_table(path).to_pylist()
            meta = {'transport': 'pinned_parquet', 'revision': HF_REVISION,
                    'file_sha256': file_hash(path)}
            # El hash fijado se obtuvo del Viewer; si la representación Parquet difiere
            # (tipos numéricos), se intenta el Viewer antes de declarar el catálogo distinto.
            if digest(sorted(rows, key=lambda r: (r['subset_name'], r['instance_id']))) != ROWS_SHA:
                warnings.warn('Parquet no coincide con el hash fijado; comprobando snapshot oficial Viewer.')
                rows = None
        except Exception as exc:
            warnings.warn(f'Parquet no disponible ({type(exc).__name__}); comprobando snapshot oficial Viewer.')
        if rows is None:
            rows = []
            for offset in range(0, 560, 100):
                url = ('https://datasets-server.huggingface.co/rows?dataset=MBZUAI%2Fsvrp-bench'
                       f'&config=default&split=test&offset={offset}&length=100')
                path = download(url, cache / f'viewer_{offset}.json')
                page = json.loads(path.read_text())
                if page.get('partial') or page['num_rows_total'] != 560:
                    raise ValueError('El catálogo cambió o está incompleto. Auditar antes de continuar.')
                for item in page['rows']:
                    if item.get('truncated_cells'):
                        raise ValueError('Viewer truncó celdas. Se necesita el Parquet completo.')
                    rows.append(item['row'])
            meta = {'transport': 'viewer_content_verified', 'revision': None,
                    'snapshot_observed': '2026-09-16', 'requested_revision': HF_REVISION}
    rows = sorted(rows, key=lambda r: (r['subset_name'], r['instance_id']))
    if len(rows) != 560 or digest(rows) != ROWS_SHA:
        raise ValueError('Hash del catálogo distinto. No seleccionar datos nuevos silenciosamente.')
    meta.update(dataset='MBZUAI/svrp-bench', split='test', rows_sha256=ROWS_SHA,
                rows=len(rows), role='development_only_never_final_test')
    write_json(snapshot, rows)
    write_json(meta_file, meta)
    return rows, meta


def upstream_modules(root):
    directory = str((Path(root) / 'vrp_bench').resolve())
    if directory not in sys.path:
        sys.path.insert(0, directory)
    for name in ('constants', 'city', 'common', 'time_windows_generator'):
        mod = importlib.import_module(name)
        if Path(mod.__file__).resolve().parent != Path(directory):
            raise RuntimeError(f'Módulo {name} procede de otra ruta; reinicie el entorno.')
    return sys.modules['common'], sys.modules['time_windows_generator']


@dataclass(frozen=True)
class Instance:
    instance_id: str
    locations: np.ndarray
    demands: np.ndarray
    capacities: np.ndarray
    windows: np.ndarray
    appear_times: np.ndarray
    provenance: dict

    @property
    def n(self):
        return len(self.demands) - 1

    def payload(self):
        return {'instance_id': self.instance_id, 'depot_indices': [0],
                **{key: getattr(self, key).tolist() for key in
                   ('locations', 'demands', 'capacities', 'windows', 'appear_times')},
                'provenance': self.provenance}

    @property
    def sha(self):
        return digest(self.payload())


def freeze_instance(payload):
    if payload.get('depot_indices') != [0]:
        raise ValueError('Este piloto admite exactamente el depósito 0.')
    arrays = {}
    for field in ('locations', 'demands', 'capacities', 'windows', 'appear_times'):
        arrays[field] = np.array(payload[field], dtype=np.float64, copy=True)
        arrays[field].setflags(write=False)
    x = Instance(payload['instance_id'], **arrays, provenance=payload['provenance'])
    n = x.n + 1
    if n < 2 or x.locations.shape != (n, 2) or x.windows.shape != (n, 2):
        raise ValueError('Dimensiones inválidas.')
    if x.demands.shape != (n,) or x.appear_times.shape != (n,) or x.capacities.ndim != 1:
        raise ValueError('Dimensiones inválidas en demanda/flota/arribos.')
    if not all(np.isfinite(v).all() for v in arrays.values()):
        raise ValueError('Datos no finitos.')
    if len(x.capacities) == 0 or np.any(x.capacities <= 0) or np.any(x.demands < 0):
        raise ValueError('Capacidades/demandas inválidas.')
    if x.demands[0] != 0 or np.any(x.appear_times < 0) or np.any(x.windows[:, 0] > x.windows[:, 1]):
        raise ValueError('Depósito, aparición o ventanas inválidos.')
    return x


def make_instance(n, rows, root, master_seed=20260916):
    common, tw = upstream_modules(root)
    subset = f'twvrp_{n}_single_depot'
    candidates = sorted([r for r in rows if r['subset_name'] == subset], key=lambda r: r['instance_id'])
    seed = seed_for(master_seed, 'geometry', n)
    if candidates:
        row = candidates[0]  # elección anterior a ejecutar cualquier solver
        raw = row
        xy, demand, appears = row['locations'], row['demands'], row['appear_times']
        caps = row['vehicle_capacities']
        if len(caps) == 1:
            caps = caps * int(row['num_vehicles'])
        if len(caps) != int(row['num_vehicles']):
            raise ValueError('Flota inconsistente; no reparar de manera implícita.')
        origin = {'kind': 'hf_geometry_demands_fleet_plus_derived_windows',
                  'subset_name': subset, 'source_instance_id': int(row['instance_id']),
                  'source_row_sha256': digest(row)}
    else:
        if n != 300:
            raise ValueError(f'Tamaño {n} sin datos publicados y sin derivación aprobada.')
        from threadpoolctl import threadpool_limits
        with legacy_seed(seed), threadpool_limits(limits=1):
            base = common.generate_base_instance(n, (1000, 1000), max(1, n // 50), 1, (0, 100), False)
        xy, demand, appears = base['locations'].tolist(), base['demands'].tolist(), base['appear_time'].tolist()
        caps = None
        raw = {'locations': xy, 'demands': demand, 'appear_times': appears, 'seed': seed}
        origin = {'kind': 'derived_official_base_generator', 'geometry_seed': seed,
                  'generator': 'common.generate_base_instance', 'num_cities': max(1, n // 50)}
    if len(xy) != n + 1:
        raise ValueError('Número de nodos inconsistente; no inferir depósitos por demanda cero.')
    windows_seed = seed_for(master_seed, 'time_windows', n)
    # Replica la regla de real_twcvrp: tipo elegido con random.randint(0,1),
    # no la proporción 60/40 descrita en el artículo. Se preserva esa diferencia.
    with legacy_seed(windows_seed):
        windows = [tw.sample_time_window(random.randint(0, 1), a) for a in appears]
    windows[0] = (0, 1440)
    # El dataset original cuantiza ventanas a uint16; se mantiene en derivados.
    windows = np.array(windows, dtype=np.uint16).tolist()
    if caps is None:
        # Equivalente a plt.hist(..., bins=24, range=(0,1440)) de get_num_vehicles.
        count = int(np.histogram(np.asarray(windows).ravel(), bins=24, range=(0, 1440))[0].max())
        caps = [float(sum(demand))] * max(1, count)
    origin.update(upstream_commit=UPSTREAM_SHA, windows_seed=windows_seed,
                  windows='derived_NOT_original_HF_windows', time_unit='minute',
                  coordinate_unit='source_map_unit', service_minutes=0,
                  customer_ids='1..n_including_zero_demands', depot_ids=[0],
                  capacity_modified=False)
    payload = dict(instance_id=f'dev_tw_n{n}_i0', depot_indices=[0], locations=xy,
                   demands=demand, capacities=caps, windows=windows, appear_times=appears,
                   provenance=origin)
    instance = freeze_instance(payload)
    expected = REFERENCE_INSTANCE_SHA.get((master_seed, n))
    if expected and instance.sha != expected:
        raise ValueError(f'Instancia n={n} distinta de la validada (probable cambio de numpy/scikit-learn). '
                         'No se sustituye en silencio: active STRICT_PINS = True en la celda 1 y ejecute de nuevo.')
    return instance, raw


def distances(x):
    # Euclídea float64: coherente con VRPSolverBase; Location.distance del generador
    # trunca a entero. Se declara la diferencia, no se mezcla entre métodos.
    return np.linalg.norm(x.locations[:, None, :] - x.locations[None, :, :], axis=-1)


def audit_instance(x, spec=None, certificate=None):
    """Cotas necesarias con viaje mínimo d/v; pasan a ser prueba sólo si fallan.

    Incluye apertura y regreso: un cliente puede ser alcanzable antes del cierre
    y aun así hacer imposible el retorno, incluso visitándolo solo.
    """
    spec = spec or Traffic()
    d = distances(x)
    earliest = np.maximum.reduce([d[0] / spec.velocity, x.windows[:, 0], x.appear_times])
    impossible = np.flatnonzero(earliest > x.windows[:, 1] + 1e-9)
    impossible = [int(j) for j in impossible if j != 0]
    return_impossible = [int(j) for j in range(1, x.n + 1)
                         if earliest[j] + d[j, 0] / spec.velocity > x.windows[0, 1] + 1e-9]
    oversized = np.flatnonzero(x.demands > x.capacities.max()).tolist()
    capacity_ok = bool(x.capacities.sum() >= x.demands.sum())
    certified = certificate is not None and verify_certificate(x, certificate, spec)['strict_feasible']
    return {'instance_id': x.instance_id, 'n_customers': x.n, 'n_depots': 1,
            'available_vehicles': len(x.capacities), 'total_demand': float(x.demands.sum()),
            'zero_demand_customers': int(np.sum(x.demands[1:] == 0)),
            'capacity_min': float(x.capacities.min()),
            'capacity_nonbinding_per_vehicle': bool(np.all(x.capacities >= x.demands.sum())),
            'unreachable_by_window_lower_bound': impossible,
            'impossible_depot_return_lower_bound': return_impossible,
            'oversized_demands': oversized,
            'aggregate_capacity_sufficient': capacity_ok,
            'proven_infeasible_by_lower_bound': bool(impossible or return_impossible or oversized or not capacity_ok),
            'source_kind': x.provenance['kind'], 'sha256': x.sha,
            'feasibility_certified': bool(certified),
            'certificate_scope': 'nominal_mean_only' if certified else 'none'}


@dataclass(frozen=True)
class Traffic:
    velocity: float = 1.0
    noise_scale: float = 1.0
    accident_scale: float = 1.0
    bucket_minutes: float = 1.0
    mode: str = 'stochastic'  # stochastic / no_noise / nominal_mean (no escenarios)

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.velocity, self.bucket_minutes, self.noise_scale, self.accident_scale)) or self.velocity <= 0 or self.bucket_minutes <= 0 or self.noise_scale < 0 or self.accident_scale < 0:
            raise ValueError('Parámetros de tráfico fuera del dominio.')
        if self.mode not in ('stochastic', 'no_noise', 'nominal_mean'):
            raise ValueError('Modo de tráfico desconocido.')


def normal_pdf(t, mu, sigma):
    return math.exp(-0.5 * ((t - mu) / sigma)**2) / (sigma * math.sqrt(2 * math.pi))


def traffic_parameters(t, dist, spec):
    peak = normal_pdf(t, 480, 90) + normal_pdf(t, 1020, 90)
    base = 0.25 * (0.5 + 2 * peak) * (1 - math.exp(-dist / 50))
    mu, sigma = 0.1 * peak, (0.3 + 0.2 * peak) * spec.noise_scale
    rate = 0.05 * normal_pdf(t, 1260, 120) * spec.accident_scale
    return base, mu, sigma, rate


def expected_time(dist, t, spec):
    if dist == 0 or spec.mode == 'no_noise':
        return dist / spec.velocity
    base, mu, sigma, rate = traffic_parameters(t, dist, spec)
    return dist / spec.velocity + base * math.exp(mu + sigma * sigma / 2) + rate * 75


def travel_time(dist, t, i, j, instance_id, scenario_seed, spec):
    if dist == 0 or i == j or spec.mode == 'no_noise':
        return dist / spec.velocity
    if spec.mode == 'nominal_mean':
        return expected_time(dist, t, spec)
    base, mu, sigma, rate = traffic_parameters(t, dist, spec)
    # Flujo RNG local: método, orden de evaluación y ruta no figuran en la clave.
    # La misma arista/minuto/escenario recibe los mismos números primitivos.
    bucket = math.floor(t / spec.bucket_minutes)
    rng = np.random.default_rng(seed_for('traffic-v1', instance_id, int(scenario_seed), i, j, bucket))
    factor = math.exp(mu + sigma * rng.standard_normal())
    accidents = rng.poisson(rate)
    accident_delay = float(rng.uniform(30, 120, size=accidents).sum())
    return dist / spec.velocity + base * factor + accident_delay


def scenario_seeds(master_seed=20260916, instance_id='', split='evaluation', count=256):
    if split not in ('train', 'selection', 'evaluation') or count < 1:
        raise ValueError('Split/count inválidos.')
    return [seed_for(master_seed, 'scenario', instance_id, split, k) for k in range(count)]


def validate_routes(x, routes):
    if not isinstance(routes, (list, tuple)) or len(routes) != len(x.capacities):
        raise ValueError('Una lista por vehículo, incluidas listas vacías; nodos sin depósito.')
    flat = []
    for v, route in enumerate(routes):
        if not isinstance(route, (list, tuple)):
            raise ValueError('Cada ruta debe ser una lista de índices enteros.')
        if any(isinstance(j, bool) or not isinstance(j, (int, np.integer)) or j < 1 or j > x.n for j in route):
            raise ValueError('Cliente fuera de rango o depósito dentro de la ruta.')
        if sum(x.demands[j] for j in route) > x.capacities[v] + 1e-9:
            raise ValueError('Capacidad excedida en una ruta.')
        flat.extend(route)
    if sorted(flat) != list(range(1, x.n + 1)):
        raise ValueError('Todos los clientes, incluso demanda cero, deben aparecer exactamente una vez.')
    return True


def _reference_schedule(x, route, d, spec):
    """Horario nominal sin las ventanas antiguas, con apariciones y regreso."""
    t, i, starts = 0., 0, {}
    for j in route:
        t = max(t + expected_time(d[i, j], t, spec), float(x.appear_times[j]))
        starts[j] = t
        i = j
    return starts, t + expected_time(d[i, 0], t, spec) if route else 0.


def derive_feasible_windows(parent, spec=Traffic(), margin_fraction=.25):
    """Derivado nuevo, no recuperación de ventanas originales de SVRPBench.

    Inserción balanceada: clientes de mayor a menor distancia al depósito;
    entre inserciones que respetan capacidad y horizonte, elige menor tiempo
    de retorno nominal, luego menor incremento, vehículo y posición. No usa
    ventanas de clientes ni escenarios ni resultados de los métodos.

    Proyecta cada apertura al intervalo más cercano que sitúa el horario
    testigo en el interior de la ventana, conservando su duración entera.
    El margen predefinido es 1/4 de la duración, limitado por [0, horizonte].
    Si no logra construir/certificar, falla: no prueba infactibilidad global.
    """
    if not 0 <= margin_fraction < .5:
        raise ValueError('Margen fuera de [0, .5).')
    if parent.windows[0, 0] != 0:
        raise ValueError('Este protocolo exige apertura del depósito en 0.')
    nominal = Traffic(**(asdict(spec) | {'mode': 'nominal_mean'}))
    d, horizon = distances(parent), float(parent.windows[0, 1])
    routes = [[] for _ in parent.capacities]
    loads, returns = np.zeros(len(routes)), np.zeros(len(routes))
    for j in sorted(range(1, parent.n + 1), key=lambda k: (-d[0, k], k)):
        choices = []
        for v, route in enumerate(routes):
            if loads[v] + parent.demands[j] > parent.capacities[v] + 1e-9:
                continue
            for pos in range(len(route) + 1):
                candidate = route[:pos] + [j] + route[pos:]
                _, end = _reference_schedule(parent, candidate, d, nominal)
                if end <= horizon + 1e-9:
                    choices.append(((end, end - returns[v], v, pos), v, candidate, end))
        if not choices:
            raise ValueError(f'No se pudo construir testigo para cliente {j}; no cambiar flota/horizonte. '
                             'No constituye prueba de infactibilidad global.')
        _, v, routes[v], returns[v] = min(choices)
        loads[v] += parent.demands[j]
    validate_routes(parent, routes)
    windows = parent.windows.copy()
    for route in routes:
        starts, _ = _reference_schedule(parent, route, d, nominal)
        for j, t in starts.items():
            width = float(parent.windows[j, 1] - parent.windows[j, 0])
            if width < 2 or width != int(width) or width > horizon or horizon != int(horizon):
                raise ValueError('Proyección requiere duración entera >=2 y <= horizonte entero.')
            margin = min(margin_fraction * width, t, horizon - t)
            lower = max(0, math.ceil(t - width + margin - 1e-9))
            upper = min(int(horizon - width), math.floor(t - margin + 1e-9))
            if lower > upper:
                raise ValueError('No hay proyección entera admisible; no ensanchar ventanas.')
            opening = min(max(int(parent.windows[j, 0]), lower), upper)
            windows[j] = [opening, opening + width]
    shifts = windows[1:, 0] - parent.windows[1:, 0]
    transformation = {'policy': WINDOW_POLICY, 'margin_fraction': margin_fraction,
                      'parent_instance_sha256': parent.sha, 'nominal_traffic': asdict(nominal),
                      'changed_windows': int(np.count_nonzero(shifts)),
                      'mean_absolute_shift_minutes': float(np.abs(shifts).mean()),
                      'max_absolute_shift_minutes': float(np.abs(shifts).max()),
                      'window_widths_preserved': True, 'geometry_demands_fleet_preserved': True,
                      'uses_evaluation_scenarios': False}
    payload = parent.payload()
    payload.update(instance_id=parent.instance_id + '_fw_v2', windows=windows.tolist(),
                   provenance=dict(parent.provenance, kind='nominal_feasible_derived_windows',
                                   parent_kind=parent.provenance['kind'],
                                   windows='derived_projected_NOT_original_HF_windows',
                                   transformation=transformation))
    instance = freeze_instance(payload)
    if (parent.sha == REFERENCE_INSTANCE_SHA.get((20260916, parent.n))
            and spec == Traffic() and margin_fraction == .25
            and instance.sha != REFERENCE_FEASIBLE_SHA[parent.n]):
        raise ValueError('Derivado v2 distinto de la referencia; banco rechazado. '
                         'Compruebe código/entorno; STRICT_PINS permite reproducir el entorno validado.')
    certificate = {'scope': 'nominal_mean_only', 'not_a_competitive_baseline': True,
                   'not_solver_input': True, 'policy': WINDOW_POLICY,
                   'parent_instance_sha256': parent.sha, 'instance_sha256': instance.sha,
                   'traffic': asdict(nominal), 'routes': routes}
    certificate['verification'] = verify_certificate(instance, certificate, spec)
    return instance, certificate


def verify_certificate(x, certificate, spec=Traffic()):
    """Recalcula el testigo con el evaluador común; no confía en un booleano guardado."""
    nominal = Traffic(**(asdict(spec) | {'mode': 'nominal_mean'}))
    if certificate.get('instance_sha256') != x.sha or certificate.get('traffic') != asdict(nominal):
        raise ValueError('Certificado corresponde a otra instancia o parametrización de tráfico.')
    if certificate.get('scope') != 'nominal_mean_only':
        raise ValueError('Alcance de certificado no reconocido.')
    result = simulate(x, certificate['routes'], 0, nominal, 'fixed_order', trace=True)
    if not result['strict_feasible']:
        raise ValueError('El testigo no satisface ventanas/regreso nominales; banco rechazado.')
    slack = [x.windows[e['to'], 1] - e['service_start'] for e in result['events'] if e['to'] != 0]
    return {'strict_feasible': True, 'used_vehicles': result['used_vehicles'],
            'minimum_customer_slack_minutes': float(min(slack)),
            'maximum_return_minutes': float(max(e['arrival'] for e in result['events'] if e['to'] == 0)),
            'travel_minutes': result['travel_minutes'], 'waiting_minutes': result['waiting_minutes']}


def diagnostic_greedy(x, spec=Traffic()):
    """Heurística de arranque, no baseline del artículo ni óptimo.

    Ordena clientes por cierre; asigna a la ruta con menor tardanza proyectada,
    incremento de distancia y llegada, en ese orden lexicográfico. Sin escenarios.
    """
    d = distances(x)
    routes = [[] for _ in x.capacities]
    times = np.zeros(len(routes)); loads = np.zeros(len(routes))
    for j in sorted(range(1, x.n + 1), key=lambda k: (x.windows[k, 1], k)):
        choices = []
        for v, route in enumerate(routes):
            if loads[v] + x.demands[j] > x.capacities[v] + 1e-9:
                continue
            i = route[-1] if route else 0
            arrival = max(times[v] + expected_time(d[i, j], times[v], spec),
                          x.windows[j, 0], x.appear_times[j])
            late = max(0., arrival - x.windows[j, 1])
            depot_late = max(0., arrival + expected_time(d[j, 0], arrival, spec) - x.windows[0, 1])
            choices.append(((late + depot_late, d[i, j] + d[j, 0] - d[i, 0], arrival, v), v, arrival))
        if not choices:
            raise ValueError(f'Heurística no pudo asignar cliente {j}. No prueba infactibilidad global.')
        _, v, arrival = min(choices)
        routes[v].append(j); times[v] = arrival; loads[v] += x.demands[j]
    validate_routes(x, routes)
    return routes


def simulate(x, routes, scenario_seed, spec=Traffic(), policy='fixed_order', trace=False):
    """Evalúa sin filtrar incumplimientos. Recurso sólo usa reloj y medias conocidas.

    causal_edd: si siguiente cliente ya se proyecta tarde, elige entre los pendientes
    aún alcanzables el de cierre más próximo; no cambia asignación de vehículo.
    El servicio tardío se registra y continúa, no se convierte en factibilidad.
    """
    validate_routes(x, routes)
    if policy not in ('fixed_order', 'causal_edd'):
        raise ValueError('Política de recurso desconocida.')
    d = distances(x)
    travel = waiting = late_sum = overtime = base_cost = 0.
    late_nodes, changed, actual_routes, events = set(), 0, [], []
    for v, route in enumerate(routes):
        path = [0] + list(route) + [0]
        base_cost += sum(d[a, b] / spec.velocity for a, b in zip(path, path[1:]))
        pending, actual, i, t = list(route), [], 0, 0.
        while pending:
            j = pending[0]
            if policy == 'causal_edd':
                forecast = max(t + expected_time(d[i, j], t, spec), x.windows[j, 0], x.appear_times[j])
                if forecast > x.windows[j, 1]:
                    possible = [k for k in pending if max(t + expected_time(d[i, k], t, spec),
                                x.windows[k, 0], x.appear_times[k]) <= x.windows[k, 1]]
                    if possible:
                        chosen = min(possible, key=lambda k: (x.windows[k, 1], d[i, k], k))
                        changed += int(chosen != j)
                        j = chosen
            duration = travel_time(d[i, j], t, i, j, x.instance_id, scenario_seed, spec)
            arrival = t + duration
            start = max(arrival, x.windows[j, 0], x.appear_times[j])
            late = max(0., start - x.windows[j, 1])
            if late > 1e-9:
                late_nodes.add(j)
            travel += duration; waiting += start - arrival; late_sum += late
            if trace:
                events.append({'vehicle': v, 'from': i, 'to': j, 'departure': t,
                               'arrival': arrival, 'service_start': start, 'late': late})
            pending.remove(j); actual.append(j); i, t = j, start
        if route:
            duration = travel_time(d[i, 0], t, i, 0, x.instance_id, scenario_seed, spec)
            travel += duration
            overtime += max(0., t + duration - x.windows[0, 1])
            if trace:
                events.append({'vehicle': v, 'from': i, 'to': 0, 'departure': t,
                               'arrival': t + duration, 'service_start': t + duration,
                               'late': max(0., t + duration - x.windows[0, 1])})
        actual_routes.append(actual)
    result = {'scenario_seed': int(scenario_seed), 'travel_minutes': travel,
              'base_minutes': base_cost, 'net_execution_delta_minutes': travel - base_cost,
              'waiting_minutes': waiting, 'lateness_minutes': late_sum,
              'depot_overtime_minutes': overtime, 'late_customers': len(late_nodes),
              'customer_violation_fraction': len(late_nodes) / x.n,
              'strict_feasible': len(late_nodes) == 0 and overtime <= 1e-9,
              'all_customers_served': True, 'used_vehicles': sum(bool(r) for r in routes),
              'recourse_reorders': changed}
    if trace:
        result.update(events=events, realized_routes=actual_routes)
    return result


def empirical_cvar(values, alpha=.95):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all() or not 0 <= alpha < 1:
        raise ValueError('Muestra/alpha inválidos para CVaR.')
    z = float(np.sort(values)[max(0, math.ceil(alpha * len(values)) - 1)])
    return z + float(np.maximum(values - z, 0).sum()) / (len(values) * (1 - alpha))


def evaluate(x, routes, seeds, spec=Traffic(), policy='fixed_order', alpha=.95):
    before = x.sha
    started = time.perf_counter()
    records = [simulate(x, routes, s, spec, policy) for s in seeds]
    if not records or len(set(seeds)) != len(seeds):
        raise ValueError('Escenarios vacíos o repetidos.')
    assert x.sha == before, 'La instancia fue alterada.'
    costs = np.array([r['travel_minutes'] for r in records])
    summary = {'instance_id': x.instance_id, 'instance_sha256': before, 'policy': policy,
               'scenarios': len(records), 'alpha': alpha,
               'mean_travel_minutes': float(costs.mean()),
               'cvar_travel_minutes': empirical_cvar(costs, alpha),
               'cost_variance_population': float(costs.var(ddof=0)),
               'scenario_strict_feasibility': float(np.mean([r['strict_feasible'] for r in records])),
               'mean_customer_violation_fraction': float(np.mean([r['customer_violation_fraction'] for r in records])),
               'mean_lateness_minutes': float(np.mean([r['lateness_minutes'] for r in records])),
               'mean_depot_overtime_minutes': float(np.mean([r['depot_overtime_minutes'] for r in records])),
               'used_vehicles': records[0]['used_vehicles'],
               'evaluation_seconds': time.perf_counter() - started}
    return summary, records


def environment_report():
    versions = {}
    for pkg in ('numpy', 'pandas', 'matplotlib', 'scipy', 'scikit-learn', 'pillow', 'pyarrow', 'huggingface-hub', 'torch'):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    resolved = {}
    for d in importlib.metadata.distributions():
        try:
            name = d.metadata['Name']
        except Exception:  # dist-info residual de pip sin METADATA
            continue
        if name:
            resolved.setdefault(name, d.version)  # la primera en sys.path es la importada
    report = {'resolved_packages': resolved, 'python': sys.version, 'platform': platform.platform(),
              'cpu_count': os.cpu_count(), 'versions': versions}
    if shutil.which('nvidia-smi'):
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
                                 '--format=csv,noheader'], capture_output=True, text=True, timeout=15)
        report['gpu'] = result.stdout.strip()
    else:
        report['gpu'] = None
    return report


def bundle_files(directory):
    """Archivos sellables; excluye bytecode que Python crea al importar bank/code."""
    return [p for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'CHECKSUMS.json'
            and '__pycache__' not in p.relative_to(directory).parts]


def seal_bundle(directory):
    directory = Path(directory)
    manifest = {str(p.relative_to(directory)): file_hash(p) for p in bundle_files(directory)}
    write_json(directory / 'CHECKSUMS.json', manifest)
    return digest(manifest)


def verify_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'CHECKSUMS.json').read_text())
    for name, expected in manifest.items():
        path = directory / name
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f'Archivo ausente/modificado: {name}')
    actual = {str(p.relative_to(directory)) for p in bundle_files(directory)}
    if actual != set(manifest):
        raise ValueError('Archivos extra en banco sellado.')
    return digest(manifest)


def load_bank(directory):
    """Punto de entrada común para notebooks 01–06."""
    directory = Path(directory)
    verify_bundle(directory)
    frozen_code = directory / 'code' / 'svrplab_pilot.py'
    if not frozen_code.exists() or file_hash(frozen_code) != file_hash(__file__):
        raise ValueError('Evaluador diferente al banco. Importe el módulo guardado en bank/code.')
    config = json.loads((directory / 'config.json').read_text())
    if config.get('protocol_version') != PROTOCOL_VERSION:
        raise ValueError('Versión del banco incompatible; no mezclar bancos v1 y v2.')
    instances = [freeze_instance(json.loads(p.read_text())) for p in sorted((directory / 'instances').glob('*.json'))]
    if sorted(x.n for x in instances) != sorted(config['sizes']):
        raise ValueError('Tamaños del banco no coinciden con configuración.')
    for x in instances:
        certificate = json.loads((directory / f'certificates/n{x.n:04d}.json').read_text())
        verify_certificate(x, certificate, Traffic(**config['traffic']))
    return instances


def sync_verified(source, destination):
    """Copia comprobada, sin borrar origen ni sobrescribir un banco diferente."""
    source, destination = Path(source), Path(destination)
    expected = verify_bundle(source)
    if destination.exists():
        if verify_bundle(destination) != expected:
            raise ValueError(f'Ya existe otro contenido en {destination}; use otro ID.')
        return destination
    staging = destination.with_name(destination.name + '.partial')
    if staging.exists():
        raise ValueError(f'Copia interrumpida en {staging}; conservar e inspeccionar antes de reintentar.')
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, staging)
    if verify_bundle(staging) != expected:
        raise IOError('Copia no verificada; origen conservado.')
    staging.rename(destination)
    return destination
