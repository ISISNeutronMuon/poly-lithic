# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation,
# Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

"""HTTP integration tests for SimpleFastAPIInterfaceServer endpoints.

Uses FastAPI's TestClient (no real network, no uvicorn thread).
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from poly_lithic.src.interfaces.fastapi_interface import SimpleFastAPIInterfaceServer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def iface():
    """Create a FastAPI interface with server disabled and yield a TestClient."""
    cfg = {
        'name': 'http_test',
        'start_server': False,
        'input_queue_max': 5,
        'output_queue_max': 3,
        'variables': {
            'A': {'mode': 'in', 'type': 'scalar', 'default': 1.0},
            'B': {'mode': 'in', 'type': 'array', 'default': [10, 20, 30]},
            'C': {'mode': 'out', 'type': 'scalar', 'default': 0.0},
            'D': {'mode': 'inout', 'type': 'scalar', 'default': 5.0},
        },
    }
    server = SimpleFastAPIInterfaceServer(cfg)
    yield server
    server.close()


@pytest.fixture
def client(iface):
    return TestClient(iface.app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client):
        r = client.get('/health')
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'ok'
        assert body['type'] == 'interface.fastapi_server'


# ---------------------------------------------------------------------------
# GET /settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_settings_structure(self, client):
        r = client.get('/settings')
        assert r.status_code == 200
        body = r.json()
        assert 'inputs' in body
        assert 'outputs' in body
        assert 'variables' in body
        assert 'routes' in body
        assert 'A' in body['inputs']
        assert 'C' in body['outputs']

    def test_settings_variable_meta(self, client):
        r = client.get('/settings')
        body = r.json()
        assert body['variables']['A']['type'] == 'scalar'
        assert body['variables']['B']['type'] == 'array'


# ---------------------------------------------------------------------------
# POST /submit
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_submit_single(self, client):
        r = client.post('/submit', json={
            'variables': {'A': {'value': 42.0}},
        })
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'queued'
        assert 'job_id' in body
        assert 'A' in body['updated']

    def test_submit_with_custom_job_id(self, client):
        r = client.post('/submit', json={
            'job_id': 'my-job',
            'variables': {'A': {'value': 1.0}},
        })
        assert r.status_code == 200
        assert r.json()['job_id'] == 'my-job'

    def test_submit_unknown_variable(self, client):
        r = client.post('/submit', json={
            'variables': {'NONEXISTENT': {'value': 1.0}},
        })
        assert r.status_code == 404

    def test_submit_write_to_output(self, client):
        r = client.post('/submit', json={
            'variables': {'C': {'value': 1.0}},
        })
        assert r.status_code == 403

    def test_submit_type_error(self, client):
        r = client.post('/submit', json={
            'variables': {'A': {'value': 'not_a_number'}},
        })
        assert r.status_code == 422

    def test_submit_duplicate_job_id(self, client):
        client.post('/submit', json={
            'job_id': 'dup',
            'variables': {'A': {'value': 1.0}},
        })
        r = client.post('/submit', json={
            'job_id': 'dup',
            'variables': {'A': {'value': 2.0}},
        })
        assert r.status_code == 409

    def test_submit_extra_field_rejected(self, client):
        r = client.post('/submit', json={
            'variables': {'A': {'value': 1.0, 'extra_field': 'bad'}},
        })
        assert r.status_code == 422

    def test_submit_queue_full(self, client):
        # input_queue_max=5
        for i in range(5):
            r = client.post('/submit', json={
                'variables': {'A': {'value': float(i)}},
            })
            assert r.status_code == 200

        r = client.post('/submit', json={
            'variables': {'A': {'value': 99.0}},
        })
        assert r.status_code == 429

    def test_submit_with_metadata(self, client):
        r = client.post('/submit', json={
            'variables': {
                'A': {
                    'value': 1.0,
                    'timestamp': 1234567890.0,
                    'metadata': {'custom_key': 'custom_val'},
                },
            },
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /get
# ---------------------------------------------------------------------------


class TestGetEndpoint:
    def test_get_variables(self, client):
        r = client.post('/get', json={
            'variables': ['A', 'D'],
        })
        assert r.status_code == 200
        body = r.json()
        assert body['values']['A']['value'] == 1.0
        assert body['values']['D']['value'] == 5.0

    def test_get_unknown_variable(self, client):
        r = client.post('/get', json={
            'variables': ['NONEXISTENT'],
        })
        assert r.status_code == 404

    def test_get_array_returns_list(self, client):
        r = client.post('/get', json={
            'variables': ['B'],
        })
        assert r.status_code == 200
        assert r.json()['values']['B']['value'] == [10, 20, 30]

    def test_get_reflects_writes(self, client, iface):
        iface.put('A', 99.0)
        r = client.post('/get', json={'variables': ['A']})
        assert r.json()['values']['A']['value'] == 99.0


# ---------------------------------------------------------------------------
# POST /jobs (batch)
# ---------------------------------------------------------------------------


class TestJobsBatch:
    def test_batch_submit(self, client):
        r = client.post('/jobs', json={
            'jobs': [
                {'variables': {'A': {'value': 1.0}}},
                {'variables': {'A': {'value': 2.0}}},
            ],
        })
        assert r.status_code == 200
        body = r.json()
        assert len(body['accepted']) == 2

    def test_batch_duplicate_within(self, client):
        r = client.post('/jobs', json={
            'jobs': [
                {'job_id': 'same', 'variables': {'A': {'value': 1.0}}},
                {'job_id': 'same', 'variables': {'A': {'value': 2.0}}},
            ],
        })
        assert r.status_code == 409

    def test_batch_atomic_validation(self, client, iface):
        """If second job has bad variable, nothing should be enqueued."""
        r = client.post('/jobs', json={
            'jobs': [
                {'variables': {'A': {'value': 1.0}}},
                {'variables': {'NONEXISTENT': {'value': 2.0}}},
            ],
        })
        assert r.status_code == 404
        # Nothing was enqueued
        assert len(iface._queued) == 0


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


class TestGetJobById:
    def test_get_job(self, client):
        r = client.post('/submit', json={
            'job_id': 'j1',
            'variables': {'A': {'value': 1.0}},
        })
        assert r.status_code == 200

        r = client.get('/jobs/j1')
        assert r.status_code == 200
        body = r.json()
        assert body['job_id'] == 'j1'
        assert body['status'] == 'queued'

    def test_unknown_job_id(self, client):
        r = client.get('/jobs/nonexistent')
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/next
# ---------------------------------------------------------------------------


class TestJobsNext:
    def test_no_completed_jobs(self, client):
        r = client.get('/jobs/next')
        assert r.status_code == 404

    def test_next_returns_completed(self, client, iface):
        # Submit, consume, complete
        client.post('/submit', json={
            'job_id': 'j-next',
            'variables': {'A': {'value': 1.0}},
        })
        iface.get_many([], consume_jobs=True)
        iface.put_many({
            'C': {
                'value': 42.0,
                'metadata': {'trace': {'job_id': 'j-next'}},
            },
        })

        r = client.get('/jobs/next')
        assert r.status_code == 200
        body = r.json()
        assert body['job_id'] == 'j-next'
        assert body['status'] == 'completed'

    def test_next_dequeues(self, client, iface):
        """After GET /jobs/next the same job should not appear again."""
        client.post('/submit', json={
            'job_id': 'j-once',
            'variables': {'A': {'value': 1.0}},
        })
        iface.get_many([], consume_jobs=True)
        iface.put_many({
            'C': {
                'value': 1.0,
                'metadata': {'trace': {'job_id': 'j-once'}},
            },
        })

        r1 = client.get('/jobs/next')
        assert r1.status_code == 200
        r2 = client.get('/jobs/next')
        assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Full job round-trip
# ---------------------------------------------------------------------------


class TestJobRoundTrip:
    def test_submit_consume_complete_poll(self, client, iface):
        # 1. Submit
        r = client.post('/submit', json={
            'job_id': 'round-trip',
            'variables': {'A': {'value': 3.14}},
        })
        assert r.status_code == 200

        # 2. Consume jobs (simulates InterfaceObserver.get_all path)
        batch = iface.get_many([], consume_jobs=True)
        assert isinstance(batch, list)
        assert len(batch) == 1

        # 3. Pipeline writes output
        iface.put_many({
            'C': {
                'value': 6.28,
                'metadata': {'trace': {'job_id': 'round-trip'}},
            },
        })

        # 4. Poll by ID
        r = client.get('/jobs/round-trip')
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'completed'
        assert body['outputs']['C']['value'] == 6.28

        # 5. Poll next completed
        r = client.get('/jobs/next')
        assert r.status_code == 200
        assert r.json()['job_id'] == 'round-trip'

    def test_clock_driven_round_trip_no_metadata(self, client, iface):
        """Simulates the real clock-driven pipeline where transformers
        strip metadata. Jobs should still complete via FIFO matching."""
        # 1. Submit
        r = client.post('/submit', json={
            'job_id': 'clock-trip',
            'variables': {'A': {'value': 10.0}},
        })
        assert r.status_code == 200

        # 2. Clock tick: get_many (default path) transitions queued→running
        iface.get_many(iface.get_inputs())

        # Verify job is now running
        r = client.get('/jobs/clock-trip')
        assert r.json()['status'] == 'running'

        # 3. Pipeline output arrives WITHOUT metadata (transformers strip it)
        iface.put_many({
            'C': {'value': 20.0},
        })

        # 4. Job should be completed via FIFO
        r = client.get('/jobs/clock-trip')
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'completed'
        assert body['outputs']['C']['value'] == 20.0


# ---------------------------------------------------------------------------
# Numpy serialisation
# ---------------------------------------------------------------------------


class TestNumpySerialization:
    def test_array_serialized_as_list(self, client):
        r = client.post('/get', json={'variables': ['B']})
        val = r.json()['values']['B']['value']
        assert isinstance(val, list)
        assert val == [10, 20, 30]

    def test_settings_array_current(self, client):
        r = client.get('/settings')
        current = r.json()['variables']['B']['current']
        assert isinstance(current, list)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCORS:
    def test_cors_headers_when_configured(self):
        cfg = {
            'name': 'cors_test',
            'start_server': False,
            'cors_origins': ['http://localhost:3000'],
            'variables': {
                'X': {'mode': 'in', 'type': 'scalar'},
            },
        }
        server = SimpleFastAPIInterfaceServer(cfg)
        tc = TestClient(server.app)
        r = tc.options(
            '/health',
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'GET',
            },
        )
        assert 'access-control-allow-origin' in r.headers
        server.close()

    def test_no_cors_by_default(self, client):
        r = client.get('/health', headers={'Origin': 'http://evil.com'})
        assert 'access-control-allow-origin' not in r.headers
