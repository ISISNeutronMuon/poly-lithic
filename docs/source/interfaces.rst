Interfaces Guide
================

This page explains how to use interfaces in your project.

Overview
--------
Interfaces are used to connect to different data sources. They follow the
:class:`~poly_lithic.src.interfaces.BaseInterface.BaseInterface` contract,
providing ``get``, ``put``, ``get_many``, ``put_many`` and ``monitor`` methods.

Available Interfaces
--------------------
- :class:`~poly_lithic.src.interfaces.BaseInterface.BaseInterface`
- :class:`~poly_lithic.src.interfaces.p4p_interface.SimplePVAInterface`
- :class:`~poly_lithic.src.interfaces.fastapi_interface.SimpleFastAPIInterfaceServer`

EPICS Interfaces (p4p / p4p_server)
------------------------------------
The ``p4p`` interface connects to an external EPICS server. The ``p4p_server``
interface hosts its own p4p server for the specified PVs. Both share the same
YAML configuration format. See the README for sample YAML.

EPICS Variable Fields
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 18 10 15 57

   * - Field
     - Type
     - Default
     - Description
   * - ``proto``
     - string
     - **required**
     - Protocol (currently ``pva``)
   * - ``name``
     - string
     - **required**
     - PV name
   * - ``mode``
     - string
     - ``"inout"``
     - ``in``, ``out``, or ``inout``
   * - ``type``
     - string
     - ``"scalar"``
     - ``scalar``, ``waveform``, ``array``, ``image``
   * - ``default``
     - any
     - ``0.0`` / zeros
     - Initial value (not supported for ``image`` type)
   * - ``length``
     - int
     - ``10``
     - Array/waveform length when no default is provided
   * - ``image_size``
     - dict
     - —
     - Required for ``image`` type: ``{"x": int, "y": int}``
   * - ``compute_alarm``
     - bool
     - ``false``
     - Enable scalar alarm computation from ``valueAlarm`` limits
   * - ``display``
     - dict
     - —
     - Optional NTScalar display metadata
   * - ``control``
     - dict
     - —
     - Optional NTScalar control metadata
   * - ``valueAlarm``
     - dict
     - —
     - Optional NTScalar alarm limit metadata

Alarm Behavior
~~~~~~~~~~~~~~

- Computation is scalar-only and active when ``compute_alarm: true``.
- ``compute_alarm: true`` requires:
  ``valueAlarm.active: true`` and limits
  ``lowAlarmLimit``, ``lowWarningLimit``, ``highWarningLimit``, ``highAlarmLimit``.
- Missing severities use defaults:
  ``lowAlarmSeverity=2``, ``lowWarningSeverity=1``,
  ``highWarningSeverity=1``, ``highAlarmSeverity=2``.
- Status mapping follows EPICS ``menuAlarmStat``:
  ``NO_ALARM=0``, ``HIHI=3``, ``HIGH=4``, ``LOLO=5``, ``LOW=6``.
- Explicit ``alarm`` payload overrides computed alarm.
- Non-scalars do not compute alarms, but explicit ``alarm`` payloads are accepted.
- ``p4p`` client attempts a structured put first; if the target rejects it, it
  retries with a value-only put.

Model Alarm Override
~~~~~~~~~~~~~~~~~~~~

Models can publish structured output with explicit alarm fields (for example
``{"PV": {"value": 1.0, "alarm": {...}}}``), and ``ModelObserver`` preserves
that structure when publishing downstream.

In ``examples/base/local/deployment_config_p4p_alarm.yaml`` this passes through
an ``output_transformer`` direct-symbol mapping
(``ML:LOCAL:TEST_S -> ML:LOCAL:TEST_S``), which preserves ``alarm`` and other
non-``value`` fields.

See example:

- ``examples/base/local/deployment_config_p4p_alarm.yaml``
- ``examples/base/local/model_definition_alarm_override.py``

k2eg Interface
--------------
Built on SLAC's `k2eg <https://github.com/slaclab/k2eg>`_, this interface gets
data from ``pva`` and ``ca`` protocols over Kafka. See the README for sample
YAML.

FastAPI Interface (fastapi_server)
----------------------------------
The ``fastapi_server`` interface exposes a REST API for submitting inference
jobs and retrieving results. It manages an internal job queue and variable
store, and embeds a uvicorn server.

.. warning::

  ``fastapi_server`` is experimental and may change or be removed without
  notice.

Register it in your YAML config with ``type: "interface.fastapi_server"``.

Configuration Fields
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 10 15 55

   * - Field
     - Type
     - Default
     - Description
   * - ``name``
     - string
     - ``"fastapi_server"``
     - Display name
   * - ``host``
     - string
     - ``"127.0.0.1"``
     - Bind address
   * - ``port``
     - int
     - ``8000``
     - Bind port
   * - ``start_server``
     - bool
     - ``true``
     - Whether to launch embedded uvicorn
   * - ``wait_for_server_start``
     - bool
     - ``false``
     - Block until server is accepting connections
   * - ``startup_timeout_s``
     - float
     - ``2.0``
     - Max wait for startup
   * - ``input_queue_max``
     - int
     - ``1000``
     - Max queued jobs before rejecting (HTTP 429)
   * - ``output_queue_max``
     - int
     - ``1000``
     - Max completed jobs before oldest is evicted
   * - ``cors_origins``
     - list[string]
     - ``[]``
     - CORS allow-origins (empty = no CORS middleware)
   * - ``variables``
     - dict
     - **required**
     - Variable definitions (see below)

Variable Fields
~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 15 10 15 60

   * - Field
     - Type
     - Default
     - Description
   * - ``mode``
     - string
     - ``"inout"``
     - ``in``, ``out``, or ``inout``
   * - ``type``
     - string
     - ``"scalar"``
     - ``scalar``, ``waveform``, ``array``, or ``image``
   * - ``default``
     - any
     - ``0.0`` / zeros
     - Initial value (not supported for ``image`` type)
   * - ``length``
     - int
     - ``10``
     - Array/waveform length when no default is provided
   * - ``image_size``
     - dict
     - —
     - Required for ``image`` type: ``{"x": int, "y": int}``

Example YAML
~~~~~~~~~~~~

.. code-block:: yaml

   modules:
     my_fastapi:
       name: "my_fastapi"
       type: "interface.fastapi_server"
       pub: "in_interface"
       sub:
         - "get_all"
         - "out_transformer"
       config:
         name: "my_fastapi_interface"
         host: "127.0.0.1"
         port: 8000
         start_server: true
         input_queue_max: 1000
         output_queue_max: 1000
         cors_origins:
           - "http://localhost:3000"
         variables:
           MY_INPUT_A:
             mode: in
             type: scalar
             default: 0.0
           MY_INPUT_B:
             mode: in
             type: array
             default: [1, 2, 3, 4, 5]
           MY_OUTPUT:
             mode: out
             type: scalar
             default: 0.0

REST API Endpoints
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 10 20 70

   * - Method
     - Path
     - Description
   * - ``GET``
     - ``/health``
     - Health check — returns ``{"status": "ok", "type": "interface.fastapi_server"}``
   * - ``GET``
     - ``/settings``
     - Variable metadata, queue limits, and route table
   * - ``POST``
     - ``/submit``
     - Submit a single inference job
   * - ``POST``
     - ``/get``
     - Read current variable values
   * - ``POST``
     - ``/jobs``
     - Submit a batch of jobs
   * - ``GET``
     - ``/jobs/next``
     - Dequeue the next completed job
   * - ``GET``
     - ``/jobs/{job_id}``
     - Get the status of a specific job

Error Codes
~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 10 90

   * - Code
     - Condition
   * - 403
     - Write to a read-only variable (``mode: out``)
   * - 404
     - Unknown variable name, unknown job ID, or no completed jobs for ``/jobs/next``
   * - 409
     - Duplicate job ID
   * - 422
     - Type validation failure (e.g. wrong shape, non-numeric value)
   * - 429
     - Input queue full

Job Lifecycle & Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~

Jobs submitted via ``/submit`` or ``/jobs`` follow this lifecycle::

   submit → queued → running → completed

1. **Queued** — the job is validated and placed in the input queue.
2. **Running** — on each clock tick, **one** queued job is transitioned to
   running and its input values are loaded into the variable store for the
   pipeline to process.
3. **Completed** — when the pipeline writes results back via ``put_many``, the
   oldest running job is marked as completed and its outputs are recorded.

Completed jobs can be retrieved via ``GET /jobs/next`` (FIFO dequeue) or
``GET /jobs/{job_id}`` (by ID).

.. note::

   **Current tracking limitation (Stage 1 / v1.7.3+):**
   Job tracking is currently approximated using FIFO ordering. The pipeline's
   transformers strip message metadata, so the ``job_id`` is typically not
   propagated through to ``put_many``. Instead, the system uses a FIFO
   fallback: the oldest running job is assumed to be the one that completed.
   To enforce this assumption, the clock-driven path transitions only **one
   queued job per tick** to running state.

   This is reliable for single-job-at-a-time workloads but does not support
   true concurrent job tracking.

   **Planned improvement (Stage 2 / v1.8+):**
   Proper job tracking will be integrated via trace propagation across the
   message broker. Each job's ``job_id`` will be carried through the full
   pipeline in struct metadata, enabling accurate matching of results to jobs
   even under concurrent load.
