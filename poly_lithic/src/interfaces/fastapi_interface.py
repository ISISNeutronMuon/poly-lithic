"""
FastAPI Interface — Stage 1 (v1.7.3 baseline)

Provides an HTTP interface to the poly-lithic pipeline via FastAPI.
Supports variable read/write, job submission, batch jobs, and polling.
"""

import copy
import threading
import time
import uuid
from collections import deque
from typing import Any, Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from poly_lithic.src.interfaces.BaseInterface import BaseInterface
from poly_lithic.src.logging_utils import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class VariableStruct(BaseModel):
    """Single variable value with optional timestamp and metadata.

    The ``metadata`` field is the future carrier for trace information —
    in Stage 1 it is accepted, stored, and passed through but not interpreted.
    """

    model_config = ConfigDict(extra='forbid')

    value: Any
    timestamp: Optional[float] = None
    metadata: Optional[dict] = None


class SubmitRequest(BaseModel):
    """POST /submit body."""

    model_config = ConfigDict(extra='forbid')

    job_id: Optional[str] = None
    variables: dict[str, VariableStruct]


class GetRequest(BaseModel):
    """POST /get body."""

    model_config = ConfigDict(extra='forbid')

    job_id: Optional[str] = None
    variables: list[str]


class JobInput(BaseModel):
    """Single job inside a batch ``POST /jobs`` request."""

    model_config = ConfigDict(extra='forbid')

    job_id: Optional[str] = None
    variables: dict[str, VariableStruct]


class JobsRequest(BaseModel):
    """POST /jobs body."""

    model_config = ConfigDict(extra='forbid')

    jobs: list[JobInput]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _numpy_to_native(obj):
    """Recursively convert numpy types to JSON-safe Python natives."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _numpy_to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_numpy_to_native(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Interface implementation
# ---------------------------------------------------------------------------


class SimpleFastAPIInterfaceServer(BaseInterface):
    """HTTP interface backed by FastAPI with an in-memory job queue.

    Registered as ``"fastapi_server"`` so it can be referenced in the YAML
    config as ``type: "interface.fastapi_server"``.
    """

    def __init__(self, config: dict):
        # -- config fields with defaults --------------------------------
        self._name = config.get('name', 'fastapi_server')
        self._host = config.get('host', '127.0.0.1')
        self._port = int(config.get('port', 8000))
        self._start_server = config.get('start_server', True)
        self._wait_for_start = config.get('wait_for_server_start', False)
        self._startup_timeout = float(config.get('startup_timeout_s', 2.0))
        self._input_queue_max = int(config.get('input_queue_max', 1000))
        self._output_queue_max = int(config.get('output_queue_max', 1000))
        self._cors_origins: list[str] = config.get('cors_origins', [])

        logger.warning(
            'fastapi_server is experimental and may change or be removed without notice.'
        )

        # -- variable state ---------------------------------------------
        self._lock = threading.RLock()
        self._var_store: dict[str, Any] = {}
        self._var_meta: dict[str, dict] = {}  # {name: {mode, type, length?, image_size?}}
        self._in_list: list[str] = []
        self._out_list: list[str] = []

        self._init_variables(config.get('variables', {}))

        # -- job state ---------------------------------------------------
        self._jobs: dict[str, dict] = {}
        self._queued: deque = deque()
        self._completed: deque = deque()

        # -- monitor callback slot (Stage 2 hook) -----------------------
        self._monitor_callback = None

        # -- build FastAPI app ------------------------------------------
        self.app = self._build_app()

        # -- optional embedded server -----------------------------------
        self._server = None
        self._server_thread = None
        if self._start_server:
            self._launch_server()

    # -------------------------------------------------------------------
    # Variable initialisation
    # -------------------------------------------------------------------

    def _init_variables(self, variables: dict):
        for name, vdef in variables.items():
            mode = vdef.get('mode', 'inout')
            if mode not in ('in', 'out', 'inout'):
                raise ValueError(f'Invalid mode "{mode}" for variable {name}')

            vtype = vdef.get('type', 'scalar')
            meta: dict[str, Any] = {'mode': mode, 'type': vtype}

            if vtype == 'scalar':
                default = float(vdef['default']) if 'default' in vdef else 0.0
                self._var_store[name] = default

            elif vtype in ('waveform', 'array'):
                length = int(vdef.get('length', 10))
                meta['length'] = length
                if 'default' in vdef:
                    arr = np.array(vdef['default'])
                    self._var_store[name] = arr
                    meta['length'] = len(arr)
                else:
                    self._var_store[name] = np.zeros(length, dtype=np.float64)

            elif vtype == 'image':
                if 'default' in vdef:
                    raise NotImplementedError(
                        'Default values for images not implemented'
                    )
                img_size = vdef.get('image_size', {})
                x = int(img_size.get('x', 1))
                y = int(img_size.get('y', 1))
                meta['image_size'] = {'x': x, 'y': y}
                self._var_store[name] = np.zeros((y, x), dtype=np.float64)

            else:
                raise TypeError(f'Unknown variable type for {name}: {vtype}')

            self._var_meta[name] = meta

            if mode in ('in', 'inout'):
                self._in_list.append(name)
            if mode in ('out', 'inout'):
                self._out_list.append(name)

    # -------------------------------------------------------------------
    # Type coercion / validation
    # -------------------------------------------------------------------

    def _coerce_for_type(self, name: str, value: Any) -> Any:
        """Validate and coerce *value* for the declared type of *name*.

        Returns the coerced value or raises ``ValueError`` / ``TypeError``.
        """
        meta = self._var_meta[name]
        vtype = meta['type']

        if vtype == 'scalar':
            if isinstance(value, np.generic):
                value = value.item()
            if not isinstance(value, (int, float, bool)):
                raise TypeError(
                    f'Variable {name} (scalar) requires numeric/bool, got {type(value).__name__}'
                )
            return float(value) if not isinstance(value, bool) else value

        elif vtype in ('waveform', 'array'):
            arr = np.asarray(value)
            if arr.ndim != 1:
                raise ValueError(
                    f'Variable {name} ({vtype}) requires 1-D data, got {arr.ndim}-D'
                )
            if not np.issubdtype(arr.dtype, np.number) and arr.dtype != np.bool_:
                raise TypeError(
                    f'Variable {name} ({vtype}) requires numeric/bool dtype, got {arr.dtype}'
                )
            expected_len = meta.get('length')
            if expected_len is not None and len(arr) != expected_len:
                raise ValueError(
                    f'Variable {name} ({vtype}) expects length {expected_len}, got {len(arr)}'
                )
            return arr

        elif vtype == 'image':
            arr = np.asarray(value)
            if arr.ndim != 2:
                raise ValueError(
                    f'Variable {name} (image) requires 2-D data, got {arr.ndim}-D'
                )
            if not np.issubdtype(arr.dtype, np.number) and arr.dtype != np.bool_:
                raise TypeError(
                    f'Variable {name} (image) requires numeric/bool dtype, got {arr.dtype}'
                )
            img_size = meta.get('image_size')
            if img_size:
                expected_shape = (img_size['y'], img_size['x'])
                if arr.shape != expected_shape:
                    raise ValueError(
                        f'Variable {name} (image) expects shape {expected_shape}, got {arr.shape}'
                    )
            return arr

        raise TypeError(f'Unknown type "{vtype}" for variable {name}')

    def _check_mode(self, name: str, enforce: bool = True):
        """Raise ``PermissionError`` if variable is output-only and *enforce* is True."""
        if enforce and self._var_meta[name]['mode'] == 'out':
            raise PermissionError(f'Variable {name} is read-only (mode=out)')

    # -------------------------------------------------------------------
    # Job queue management
    # -------------------------------------------------------------------

    def _enqueue_jobs(self, jobs_input: list[JobInput]) -> list[dict]:
        """Atomically validate and enqueue a batch of jobs.

        Returns a list of ``{job_id, status}`` dicts for all accepted jobs.
        Raises ``HTTPException`` on validation or capacity errors.
        """
        with self._lock:
            # -- Phase 1: pre-validate everything -----------------------
            resolved_jobs: list[tuple[str, dict[str, VariableStruct]]] = []

            seen_ids: set[str] = set()
            for ji in jobs_input:
                jid = ji.job_id or str(uuid.uuid4())
                if jid in self._jobs or jid in seen_ids:
                    raise HTTPException(status_code=409, detail=f'Duplicate job_id: {jid}')
                seen_ids.add(jid)

                for vname, struct in ji.variables.items():
                    if vname not in self._var_meta:
                        raise HTTPException(
                            status_code=404, detail=f'Unknown variable: {vname}'
                        )
                    if self._var_meta[vname]['mode'] == 'out':
                        raise HTTPException(
                            status_code=403,
                            detail=f'Variable {vname} is read-only (mode=out)',
                        )
                    try:
                        self._coerce_for_type(vname, struct.value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(status_code=422, detail=str(exc))

                resolved_jobs.append((jid, ji.variables))

            # -- Phase 2: capacity check --------------------------------
            if len(self._queued) + len(resolved_jobs) > self._input_queue_max:
                raise HTTPException(
                    status_code=429,
                    detail='Input queue full',
                )

            # -- Phase 3: enqueue ---------------------------------------
            accepted: list[dict] = []
            for jid, variables in resolved_jobs:
                now = time.time()
                input_snapshot: dict[str, dict] = {}
                updated_vars: list[str] = []

                for vname, struct in variables.items():
                    coerced = self._coerce_for_type(vname, struct.value)
                    self._var_store[vname] = coerced

                    input_snapshot[vname] = {
                        'value': copy.deepcopy(coerced if not isinstance(coerced, np.ndarray) else coerced.copy()),
                        'timestamp': struct.timestamp or now,
                        'metadata': dict(struct.metadata) if struct.metadata else {},
                    }
                    updated_vars.append(vname)

                job_record = {
                    'job_id': jid,
                    'status': 'queued',
                    'submitted_at': now,
                    'started_at': None,
                    'completed_at': None,
                    'error': None,
                    'inputs': input_snapshot,
                    'outputs': {},
                }
                self._jobs[jid] = job_record
                self._queued.append(jid)
                accepted.append({'job_id': jid, 'status': 'queued', 'updated': updated_vars})

            # -- Phase 4: fire monitor callback -------------------------
            if self._monitor_callback is not None:
                for jid, variables in resolved_jobs:
                    snapshot = self._jobs[jid]['inputs']
                    try:
                        self._monitor_callback(snapshot)
                    except Exception:
                        logger.exception('Monitor callback error (ignored)')

        return accepted

    # -------------------------------------------------------------------
    # BaseInterface contract
    # -------------------------------------------------------------------

    def get(self, name: str, **kwargs) -> tuple[str, dict]:
        with self._lock:
            if name not in self._var_store:
                raise KeyError(f'Unknown variable: {name}')
            return name, {'value': self._var_store[name]}

    def put(self, name: str, value: Any, **kwargs) -> None:
        enforce = kwargs.get('enforce_mode', True)
        with self._lock:
            if name not in self._var_meta:
                raise KeyError(f'Unknown variable: {name}')
            self._check_mode(name, enforce=enforce)
            coerced = self._coerce_for_type(name, value)
            self._var_store[name] = coerced

    def get_many(self, data, **kwargs) -> dict | list[dict]:
        """Dual-return method.

        * ``consume_jobs=True`` with queued jobs → dequeue all, mark running,
          return a **list of dicts** (one per job with input snapshots).
        * Otherwise → return a single dict mapping requested names to values.
        """
        consume = kwargs.get('consume_jobs', False)

        with self._lock:
            if consume and self._queued:
                batch: list[dict] = []
                while self._queued:
                    jid = self._queued.popleft()
                    job = self._jobs[jid]
                    job['status'] = 'running'
                    job['started_at'] = time.time()
                    batch.append(dict(job['inputs']))
                return batch

            # Transition ONE queued job to running per clock tick.
            # The InterfaceObserver.get_all() calls this without
            # consume_jobs=True on each clock tick.  We only promote one
            # job so that each tick processes exactly one job through
            # the pipeline before the next is started.
            if self._queued:
                jid = self._queued.popleft()
                job = self._jobs[jid]
                job['status'] = 'running'
                job['started_at'] = time.time()
                # Restore this job's input values into the variable store
                # so the pipeline reads the correct inputs for this job.
                for vname, snap in job['inputs'].items():
                    self._var_store[vname] = copy.deepcopy(
                        snap['value'] if not isinstance(snap['value'], np.ndarray)
                        else snap['value'].copy()
                    )

            # Default path: return current variable values
            if isinstance(data, dict):
                names = list(data.keys())
            elif isinstance(data, (list, tuple)):
                names = list(data)
            else:
                names = [data]

            result = {}
            for name in names:
                if name in self._var_store:
                    result[name] = {'value': self._var_store[name]}
            return result

    def put_many(self, data: dict, **kwargs) -> None:
        """Write multiple variables.

        If any struct's ``metadata`` contains a ``trace.job_id`` matching a
        running job, that job is transitioned to ``completed``.
        """
        with self._lock:
            # -- Attempt to resolve a job_id from struct metadata -------
            job_id = None
            for vname, struct in data.items():
                if isinstance(struct, dict):
                    meta = struct.get('metadata')
                    if meta and isinstance(meta, dict):
                        trace = meta.get('trace')
                        if trace and isinstance(trace, dict):
                            candidate = trace.get('job_id')
                            if candidate:
                                job_id = candidate
                                break

            # -- Write variable values ----------------------------------
            for vname, struct in data.items():
                if vname not in self._var_meta:
                    logger.warning(f'put_many: unknown variable {vname}, skipping')
                    continue
                val = struct.get('value') if isinstance(struct, dict) else struct
                try:
                    coerced = self._coerce_for_type(vname, val)
                    self._var_store[vname] = coerced
                except (TypeError, ValueError) as exc:
                    logger.warning(f'put_many: coercion error for {vname}: {exc}')

            # -- Job completion -----------------------------------------
            # Stage 1 fallback: the pipeline (transformers) strips metadata,
            # so job_id will typically be None.  In that case, FIFO-complete
            # the oldest running job.
            if not job_id:
                for candidate_id, candidate_job in self._jobs.items():
                    if candidate_job['status'] == 'running':
                        job_id = candidate_id
                        break

            if job_id and job_id in self._jobs:
                job = self._jobs[job_id]
                if job['status'] == 'running':
                    now = time.time()
                    job['status'] = 'completed'
                    job['completed_at'] = now
                    # Record outputs (snapshot of output variables)
                    for vname in self._out_list:
                        val = self._var_store.get(vname)
                        if val is not None:
                            job['outputs'][vname] = {
                                'value': copy.deepcopy(val if not isinstance(val, np.ndarray) else val.copy()),
                                'timestamp': now,
                            }

                    self._completed.append(job_id)

                    # Enforce output queue capacity
                    while len(self._completed) > self._output_queue_max:
                        evicted_id = self._completed.popleft()
                        if evicted_id in self._jobs:
                            self._jobs[evicted_id]['status'] = 'failed'
                            self._jobs[evicted_id]['error'] = 'Evicted: output queue overflow'

    def get_inputs(self) -> list[str]:
        return list(self._in_list)

    def get_outputs(self) -> list[str]:
        return list(self._out_list)

    def monitor(self, handler, **kwargs) -> bool:
        """Register a single monitor callback. Returns ``True``."""
        self._monitor_callback = handler
        return True

    def close(self):
        """Shutdown the embedded uvicorn server (if running)."""
        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=2.0)
            self._server_thread = None
        logger.debug('SimpleFastAPIInterfaceServer closed')

    # -------------------------------------------------------------------
    # FastAPI app construction
    # -------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        app = FastAPI(title=self._name)

        # -- CORS -------------------------------------------------------
        if self._cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self._cors_origins,
                allow_methods=['*'],
                allow_headers=['*'],
            )

        # -- Routes -----------------------------------------------------

        @app.get('/health')
        def health():
            return {'status': 'ok', 'type': 'interface.fastapi_server'}

        @app.get('/settings')
        def settings():
            with self._lock:
                variables_meta = {}
                for name, meta in self._var_meta.items():
                    entry = dict(meta)
                    # include current value (JSON-safe)
                    entry['current'] = _numpy_to_native(self._var_store.get(name))
                    variables_meta[name] = entry

                return _numpy_to_native({
                    'name': self._name,
                    'inputs': self._in_list,
                    'outputs': self._out_list,
                    'variables': variables_meta,
                    'routes': {
                        'health': '/health',
                        'settings': '/settings',
                        'submit': '/submit',
                        'get': '/get',
                        'jobs': '/jobs',
                        'jobs_next': '/jobs/next',
                        'jobs_by_id': '/jobs/{job_id}',
                    },
                    'input_queue_max': self._input_queue_max,
                    'output_queue_max': self._output_queue_max,
                })

        @app.post('/submit')
        def submit(req: SubmitRequest):
            ji = JobInput(job_id=req.job_id, variables=req.variables)
            accepted = self._enqueue_jobs([ji])
            item = accepted[0]
            return {
                'job_id': item['job_id'],
                'status': item['status'],
                'updated': item['updated'],
            }

        @app.post('/get')
        def get_vars(req: GetRequest):
            with self._lock:
                values: dict[str, dict] = {}
                for vname in req.variables:
                    if vname not in self._var_store:
                        raise HTTPException(
                            status_code=404, detail=f'Unknown variable: {vname}'
                        )
                    values[vname] = {
                        'value': _numpy_to_native(self._var_store[vname])
                    }
                return _numpy_to_native({
                    'job_id': req.job_id or str(uuid.uuid4()),
                    'values': values,
                })

        @app.post('/jobs')
        def submit_batch(req: JobsRequest):
            accepted = self._enqueue_jobs(req.jobs)
            return {'accepted': [{'job_id': a['job_id'], 'status': a['status']} for a in accepted]}

        @app.get('/jobs/next')
        def next_completed_job():
            with self._lock:
                if not self._completed:
                    raise HTTPException(status_code=404, detail='No completed jobs')
                jid = self._completed.popleft()
                return _numpy_to_native(self._jobs[jid])

        @app.get('/jobs/{job_id}')
        def get_job(job_id: str):
            with self._lock:
                if job_id not in self._jobs:
                    raise HTTPException(status_code=404, detail=f'Unknown job_id: {job_id}')
                return _numpy_to_native(self._jobs[job_id])

        return app

    # -------------------------------------------------------------------
    # Embedded uvicorn server
    # -------------------------------------------------------------------

    def _launch_server(self):
        cfg = uvicorn.Config(
            app=self.app,
            host=self._host,
            port=self._port,
            log_level='warning',
        )
        self._server = uvicorn.Server(cfg)

        self._server_thread = threading.Thread(
            target=self._server.run,
            daemon=True,
            name=f'fastapi-{self._name}',
        )
        self._server_thread.start()

        if self._wait_for_start:
            deadline = time.time() + self._startup_timeout
            while not self._server.started and time.time() < deadline:
                time.sleep(0.01)
            if not self._server.started:
                logger.warning(
                    f'FastAPI server did not start within {self._startup_timeout}s'
                )

    # -------------------------------------------------------------------
    # Repr
    # -------------------------------------------------------------------

    def __repr__(self):
        return f'SimpleFastAPIInterfaceServer(name={self._name}, host={self._host}, port={self._port})'
