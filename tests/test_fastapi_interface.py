# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation,
# Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for SimpleFastAPIInterfaceServer (no HTTP layer)."""

import time

import numpy as np
import pytest

from poly_lithic.src.interfaces.fastapi_interface import SimpleFastAPIInterfaceServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Return a minimal config dict, merging any *overrides*."""
    cfg = {
        'name': 'test_fastapi',
        'start_server': False,  # never launch uvicorn in unit tests
        'variables': {
            'INPUT_A': {'mode': 'in', 'type': 'scalar', 'default': 1.0},
            'INPUT_B': {'mode': 'in', 'type': 'array', 'default': [1, 2, 3]},
            'OUTPUT_X': {'mode': 'out', 'type': 'scalar', 'default': 0.0},
            'INOUT_Y': {'mode': 'inout', 'type': 'scalar', 'default': 5.0},
        },
    }
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInitialisation:
    def test_class_exists(self):
        assert SimpleFastAPIInterfaceServer is not None

    def test_scalar_defaults(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        _, val = iface.get('INPUT_A')
        assert val['value'] == 1.0
        iface.close()

    def test_array_defaults(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        _, val = iface.get('INPUT_B')
        np.testing.assert_array_equal(val['value'], [1, 2, 3])
        iface.close()

    def test_array_zeros_default(self):
        cfg = _make_config(variables={
            'ARR': {'mode': 'in', 'type': 'waveform', 'length': 5},
        })
        iface = SimpleFastAPIInterfaceServer(cfg)
        _, val = iface.get('ARR')
        np.testing.assert_array_equal(val['value'], np.zeros(5))
        iface.close()

    def test_image_defaults(self):
        cfg = _make_config(variables={
            'IMG': {'mode': 'in', 'type': 'image', 'image_size': {'x': 4, 'y': 3}},
        })
        iface = SimpleFastAPIInterfaceServer(cfg)
        _, val = iface.get('IMG')
        assert val['value'].shape == (3, 4)
        iface.close()

    def test_image_custom_default_raises(self):
        cfg = _make_config(variables={
            'IMG': {
                'mode': 'in',
                'type': 'image',
                'image_size': {'x': 2, 'y': 2},
                'default': [[1, 2], [3, 4]],
            },
        })
        with pytest.raises(NotImplementedError):
            SimpleFastAPIInterfaceServer(cfg)

    def test_unknown_type_raises(self):
        cfg = _make_config(variables={
            'BAD': {'mode': 'in', 'type': 'unknown'},
        })
        with pytest.raises(TypeError):
            SimpleFastAPIInterfaceServer(cfg)

    def test_invalid_mode_raises(self):
        cfg = _make_config(variables={
            'BAD': {'mode': 'readwrite', 'type': 'scalar'},
        })
        with pytest.raises(ValueError):
            SimpleFastAPIInterfaceServer(cfg)

    def test_input_output_lists(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        assert 'INPUT_A' in iface.get_inputs()
        assert 'INPUT_B' in iface.get_inputs()
        assert 'INOUT_Y' in iface.get_inputs()
        assert 'OUTPUT_X' in iface.get_outputs()
        assert 'INOUT_Y' in iface.get_outputs()
        assert 'INPUT_A' not in iface.get_outputs()
        iface.close()


# ---------------------------------------------------------------------------
# put / get — scalars
# ---------------------------------------------------------------------------


class TestScalarPutGet:
    def test_put_and_get(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('INPUT_A', 42.0)
        _, val = iface.get('INPUT_A')
        assert val['value'] == 42.0
        iface.close()

    def test_put_bool(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('INPUT_A', True)
        _, val = iface.get('INPUT_A')
        assert val['value'] is True
        iface.close()

    def test_put_numpy_scalar(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('INPUT_A', np.float64(3.14))
        _, val = iface.get('INPUT_A')
        assert isinstance(val['value'], float)
        assert abs(val['value'] - 3.14) < 1e-9
        iface.close()

    def test_put_string_raises(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        with pytest.raises(TypeError):
            iface.put('INPUT_A', 'not_a_number')
        iface.close()


# ---------------------------------------------------------------------------
# put / get — arrays
# ---------------------------------------------------------------------------


class TestArrayPutGet:
    def test_put_list(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('INPUT_B', [10, 20, 30])
        _, val = iface.get('INPUT_B')
        np.testing.assert_array_equal(val['value'], [10, 20, 30])
        iface.close()

    def test_put_numpy(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('INPUT_B', np.array([7, 8, 9]))
        _, val = iface.get('INPUT_B')
        np.testing.assert_array_equal(val['value'], [7, 8, 9])
        iface.close()

    def test_wrong_length_raises(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        with pytest.raises(ValueError):
            iface.put('INPUT_B', [1, 2])  # expects length 3
        iface.close()

    def test_2d_raises(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        with pytest.raises(ValueError):
            iface.put('INPUT_B', [[1, 2, 3]])
        iface.close()


# ---------------------------------------------------------------------------
# put / get — images
# ---------------------------------------------------------------------------


class TestImagePutGet:
    def test_put_and_get_image(self):
        cfg = _make_config(variables={
            'IMG': {'mode': 'in', 'type': 'image', 'image_size': {'x': 3, 'y': 2}},
        })
        iface = SimpleFastAPIInterfaceServer(cfg)
        img = np.ones((2, 3))
        iface.put('IMG', img)
        _, val = iface.get('IMG')
        np.testing.assert_array_equal(val['value'], img)
        iface.close()

    def test_wrong_shape_raises(self):
        cfg = _make_config(variables={
            'IMG': {'mode': 'in', 'type': 'image', 'image_size': {'x': 3, 'y': 2}},
        })
        iface = SimpleFastAPIInterfaceServer(cfg)
        with pytest.raises(ValueError):
            iface.put('IMG', np.ones((3, 3)))  # wrong shape
        iface.close()

    def test_1d_raises(self):
        cfg = _make_config(variables={
            'IMG': {'mode': 'in', 'type': 'image', 'image_size': {'x': 3, 'y': 2}},
        })
        iface = SimpleFastAPIInterfaceServer(cfg)
        with pytest.raises(ValueError):
            iface.put('IMG', [1, 2, 3, 4, 5, 6])
        iface.close()


# ---------------------------------------------------------------------------
# Mode enforcement
# ---------------------------------------------------------------------------


class TestModeEnforcement:
    def test_write_to_output_raises(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        with pytest.raises(PermissionError):
            iface.put('OUTPUT_X', 99.0)
        iface.close()

    def test_write_to_output_with_enforce_false(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('OUTPUT_X', 99.0, enforce_mode=False)
        _, val = iface.get('OUTPUT_X')
        assert val['value'] == 99.0
        iface.close()

    def test_write_to_inout_ok(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.put('INOUT_Y', 10.0)
        _, val = iface.get('INOUT_Y')
        assert val['value'] == 10.0
        iface.close()


# ---------------------------------------------------------------------------
# get_many
# ---------------------------------------------------------------------------


class TestGetMany:
    def test_get_many_returns_dict(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        result = iface.get_many(['INPUT_A', 'INOUT_Y'])
        assert isinstance(result, dict)
        assert result['INPUT_A']['value'] == 1.0
        assert result['INOUT_Y']['value'] == 5.0
        iface.close()

    def test_get_many_consume_no_jobs(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        result = iface.get_many([], consume_jobs=True)
        # no queued jobs → returns dict (fallback path)
        assert isinstance(result, dict)
        iface.close()


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


class TestJobLifecycle:
    def _submit_one(self, iface, value=2.0, job_id=None):
        from poly_lithic.src.interfaces.fastapi_interface import JobInput, VariableStruct

        ji = JobInput(
            job_id=job_id,
            variables={'INPUT_A': VariableStruct(value=value)},
        )
        return iface._enqueue_jobs([ji])

    def test_submit_and_queued(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        accepted = self._submit_one(iface)
        assert len(accepted) == 1
        assert accepted[0]['status'] == 'queued'
        jid = accepted[0]['job_id']
        assert iface._jobs[jid]['status'] == 'queued'
        iface.close()

    def test_consume_jobs_returns_list(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        self._submit_one(iface, value=7.0)
        batch = iface.get_many([], consume_jobs=True)
        assert isinstance(batch, list)
        assert len(batch) == 1
        assert batch[0]['INPUT_A']['value'] == 7.0
        iface.close()

    def test_job_running_after_consume(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        accepted = self._submit_one(iface)
        jid = accepted[0]['job_id']
        iface.get_many([], consume_jobs=True)
        assert iface._jobs[jid]['status'] == 'running'
        iface.close()

    def test_job_running_after_clock_driven_get_many(self):
        """Default get_many (no consume_jobs) transitions queued→running."""
        iface = SimpleFastAPIInterfaceServer(_make_config())
        accepted = self._submit_one(iface)
        jid = accepted[0]['job_id']
        # simulate clock-driven get_all path
        iface.get_many(iface.get_inputs())
        assert iface._jobs[jid]['status'] == 'running'
        iface.close()

    def test_put_many_completes_job(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        accepted = self._submit_one(iface)
        jid = accepted[0]['job_id']
        iface.get_many([], consume_jobs=True)

        # simulate pipeline output with job_id in metadata
        iface.put_many({
            'OUTPUT_X': {
                'value': 42.0,
                'timestamp': time.time(),
                'metadata': {'trace': {'job_id': jid}},
            },
        })
        assert iface._jobs[jid]['status'] == 'completed'
        assert iface._jobs[jid]['outputs']['OUTPUT_X']['value'] == 42.0
        iface.close()

    def test_put_many_fifo_completes_without_metadata(self):
        """Clock-driven pipeline: put_many with no job_id in metadata
        should FIFO-complete the oldest running job."""
        iface = SimpleFastAPIInterfaceServer(_make_config())
        accepted = self._submit_one(iface, value=3.0)
        jid = accepted[0]['job_id']
        # clock-driven transition: queued → running
        iface.get_many(iface.get_inputs())
        assert iface._jobs[jid]['status'] == 'running'

        # pipeline output arrives without metadata (transformers strip it)
        iface.put_many({
            'OUTPUT_X': {'value': 99.0},
        })
        assert iface._jobs[jid]['status'] == 'completed'
        assert iface._jobs[jid]['outputs']['OUTPUT_X']['value'] == 99.0
        iface.close()

    def test_completed_job_appears_in_completed_queue(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        accepted = self._submit_one(iface)
        jid = accepted[0]['job_id']
        iface.get_many([], consume_jobs=True)
        iface.put_many({
            'OUTPUT_X': {
                'value': 1.0,
                'metadata': {'trace': {'job_id': jid}},
            },
        })
        assert jid in iface._completed
        iface.close()

    def test_duplicate_job_id_raises(self):
        from fastapi import HTTPException as FastHTTPException

        iface = SimpleFastAPIInterfaceServer(_make_config())
        self._submit_one(iface, job_id='dup-1')
        with pytest.raises(FastHTTPException) as exc_info:
            self._submit_one(iface, job_id='dup-1')
        assert exc_info.value.status_code == 409
        iface.close()

    def test_batch_multiple_jobs(self):
        from poly_lithic.src.interfaces.fastapi_interface import JobInput, VariableStruct

        iface = SimpleFastAPIInterfaceServer(_make_config())
        jobs = [
            JobInput(variables={'INPUT_A': VariableStruct(value=float(i))})
            for i in range(5)
        ]
        accepted = iface._enqueue_jobs(jobs)
        assert len(accepted) == 5
        assert len(iface._queued) == 5
        iface.close()


# ---------------------------------------------------------------------------
# Queue capacity
# ---------------------------------------------------------------------------


class TestQueueCapacity:
    def test_input_queue_full(self):
        from fastapi import HTTPException as FastHTTPException
        from poly_lithic.src.interfaces.fastapi_interface import JobInput, VariableStruct

        cfg = _make_config(input_queue_max=3)
        iface = SimpleFastAPIInterfaceServer(cfg)

        jobs = [
            JobInput(variables={'INPUT_A': VariableStruct(value=float(i))})
            for i in range(3)
        ]
        iface._enqueue_jobs(jobs)

        with pytest.raises(FastHTTPException) as exc_info:
            iface._enqueue_jobs([
                JobInput(variables={'INPUT_A': VariableStruct(value=99.0)})
            ])
        assert exc_info.value.status_code == 429
        iface.close()

    def test_output_queue_eviction(self):
        from poly_lithic.src.interfaces.fastapi_interface import JobInput, VariableStruct

        cfg = _make_config(output_queue_max=2)
        iface = SimpleFastAPIInterfaceServer(cfg)

        # Submit and complete 3 jobs
        for i in range(3):
            accepted = iface._enqueue_jobs([
                JobInput(
                    job_id=f'job-{i}',
                    variables={'INPUT_A': VariableStruct(value=float(i))},
                )
            ])
            iface.get_many([], consume_jobs=True)
            iface.put_many({
                'OUTPUT_X': {
                    'value': float(i),
                    'metadata': {'trace': {'job_id': f'job-{i}'}},
                },
            })

        # 3 completed but max is 2, so job-0 should be evicted (failed)
        assert iface._jobs['job-0']['status'] == 'failed'
        assert 'overflow' in iface._jobs['job-0']['error'].lower()
        assert len(iface._completed) == 2
        iface.close()


# ---------------------------------------------------------------------------
# Monitor callback
# ---------------------------------------------------------------------------


class TestMonitor:
    def test_register_callback(self):
        iface = SimpleFastAPIInterfaceServer(_make_config())
        calls = []
        result = iface.monitor(lambda data: calls.append(data))
        assert result is True
        iface.close()

    def test_callback_fires_on_submit(self):
        from poly_lithic.src.interfaces.fastapi_interface import JobInput, VariableStruct

        iface = SimpleFastAPIInterfaceServer(_make_config())
        calls = []
        iface.monitor(lambda data: calls.append(data))

        iface._enqueue_jobs([
            JobInput(variables={'INPUT_A': VariableStruct(value=99.0)})
        ])
        assert len(calls) == 1
        assert 'INPUT_A' in calls[0]
        iface.close()

    def test_callback_exception_does_not_fail(self):
        from poly_lithic.src.interfaces.fastapi_interface import JobInput, VariableStruct

        iface = SimpleFastAPIInterfaceServer(_make_config())
        iface.monitor(lambda data: 1 / 0)  # will raise ZeroDivisionError

        # should not raise
        iface._enqueue_jobs([
            JobInput(variables={'INPUT_A': VariableStruct(value=1.0)})
        ])
        iface.close()


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


class TestServerLifecycle:
    def test_no_server_when_disabled(self):
        iface = SimpleFastAPIInterfaceServer(_make_config(start_server=False))
        assert iface._server is None
        assert iface._server_thread is None
        iface.close()

    def test_server_starts_and_closes(self):
        cfg = _make_config(
            start_server=True,
            wait_for_server_start=True,
            startup_timeout_s=5.0,
            port=18321,  # unlikely to collide
        )
        iface = SimpleFastAPIInterfaceServer(cfg)
        assert iface._server is not None
        assert iface._server.started
        iface.close()
        # thread should have joined
        assert iface._server_thread is None
