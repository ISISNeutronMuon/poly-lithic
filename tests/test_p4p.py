# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation, Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

# from poly_lithic.src.interfaces import SimplePVAInterface
import subprocess

import numpy as np
import pytest
from poly_lithic.src.interfaces import registered_interfaces
from poly_lithic.src.logging_utils.make_logger import make_logger
import sys

SimplePVAInterface = registered_interfaces['p4p']
# start mailbox.py as a subprocess

logger = make_logger('model_manager')

process = None


# run before tests
@pytest.fixture(scope='session', autouse=True)
def setup():
    global process
    # process = subprocess.Popen(["python", "mailbox.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process = subprocess.Popen(
        [sys.executable, './tests/mailbox.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    yield
    process.kill()


def test_SimplePVAInterface_init():
    config = {
        'variables': {
            'test:float:AA': {'name': 'test:float:AA', 'proto': 'pva'},
            'test:float:BB': {'name': 'test:float:BB', 'proto': 'pva'},
        }
    }
    logger.info('Testing SimplePVAInterface init')
    p4p = SimplePVAInterface(config)
    nameA, valA = p4p.get('test:float:AA')
    assert valA['value'] == 0

    p4p.put('test:float:AA', 1)
    p4p.put('test:float:BB', 2)
    nameA, valA = p4p.get('test:float:AA')
    nameB, valB = p4p.get('test:float:BB')
    print(nameA, nameB, valA, valB)
    assert valA['value'] == 1
    assert valB['value'] == 2
    assert nameA == 'test:float:AA'
    assert nameB == 'test:float:BB'
    p4p.close()


def test_SimplePVAInterface_put_and_get_image():
    config = {
        'variables': {
            'test:image:AA': {
                'name': 'test:image:AA',
                'proto': 'pva',
                'type': 'image',
            }
        }
    }
    p4p = SimplePVAInterface(config)

    name, image_get = p4p.get('test:image:AA')
    shape = image_get['value'].shape
    print(shape)
    assert image_get['value'][0][0] == 1  # should be intialized to 1 by mailbox.py

    arry = np.random.rand(shape[0], shape[1])
    p4p.put('test:image:AA', arry)
    name, image_get = p4p.get('test:image:AA')
    print(type(image_get['value']))
    assert image_get['value'][0][0] == arry[0][0]

    p4p.close()


def test_SimplePVAInterface_put_and_get_array():
    config = {
        'variables': {
            'test:array:AA': {
                'name': 'test:array:AA',
                'proto': 'pva',
                'type': 'array',
            }
        }
    }
    p4p = SimplePVAInterface(config)

    name, array_get = p4p.get('test:array:AA')
    print(array_get['value'])
    assert type(array_get['value']) == np.ndarray
    arry = np.random.rand(10)
    p4p.put('test:array:AA', arry.tolist())
    name, array_get = p4p.get('test:array:AA')
    print(array_get)
    np.testing.assert_array_equal(array_get['value'], arry)

    p4p.close()


def test_SimplePVAInterface_reject_compute_alarm_on_non_scalar():
    config = {
        'variables': {
            'test:array:AA': {
                'name': 'test:array:AA',
                'proto': 'pva',
                'type': 'array',
                'compute_alarm': True,
                'valueAlarm': {
                    'active': True,
                    'lowAlarmLimit': -5.0,
                    'lowWarningLimit': -2.0,
                    'highWarningLimit': 2.0,
                    'highAlarmLimit': 5.0,
                    'lowAlarmSeverity': 2,
                    'lowWarningSeverity': 1,
                    'highWarningSeverity': 1,
                    'highAlarmSeverity': 2,
                },
            }
        }
    }
    with pytest.raises(ValueError, match='compute_alarm is only valid for scalar PVs'):
        SimplePVAInterface(config)


def test_SimplePVAInterface_alarm_put_fallback(monkeypatch):
    config = {
        'variables': {
            'test:float:AA': {
                'name': 'test:float:AA',
                'proto': 'pva',
                'type': 'scalar',
                'compute_alarm': True,
                'valueAlarm': {
                    'active': True,
                    'lowAlarmLimit': -5.0,
                    'lowWarningLimit': -2.0,
                    'highWarningLimit': 2.0,
                    'highAlarmLimit': 5.0,
                    'lowAlarmSeverity': 2,
                    'lowWarningSeverity': 1,
                    'highWarningSeverity': 1,
                    'highAlarmSeverity': 2,
                },
            }
        }
    }
    p4p = SimplePVAInterface(config)

    calls = []

    def fake_put(name, payload):
        calls.append((name, payload))
        if isinstance(payload, dict) and 'alarm' in payload:
            raise RuntimeError('structured put not supported')
        return None

    monkeypatch.setattr(p4p.ctxt, 'put', fake_put)

    p4p.put(
        'test:float:AA',
        {'value': 3.0, 'alarm': {'severity': 1, 'status': 4, 'message': 'HIGH'}},
    )

    assert len(calls) == 2
    assert isinstance(calls[0][1], dict)
    assert 'alarm' in calls[0][1]
    assert calls[1][1] == 3.0
    p4p.close()


def test_SimplePVAInterface_non_scalar_explicit_alarm_passthrough(monkeypatch):
    config = {
        'variables': {
            'test:array:AA': {
                'name': 'test:array:AA',
                'proto': 'pva',
                'type': 'array',
                'valueAlarm': {
                    'active': True,
                    'lowAlarmLimit': -5.0,
                    'lowWarningLimit': -2.0,
                    'highWarningLimit': 2.0,
                    'highAlarmLimit': 5.0,
                    'lowAlarmSeverity': 2,
                    'lowWarningSeverity': 1,
                    'highWarningSeverity': 1,
                    'highAlarmSeverity': 2,
                },
            }
        }
    }
    p4p = SimplePVAInterface(config)

    sent = []

    def fake_put(name, payload):
        sent.append(payload)
        return None

    monkeypatch.setattr(p4p.ctxt, 'put', fake_put)

    p4p.put(
        'test:array:AA',
        {
            'value': [1.0, 2.0, 3.0],
            'alarm': {'severity': 1, 'status': 4, 'message': 'HIGH'},
        },
    )
    p4p.put('test:array:AA', {'value': [4.0, 5.0, 6.0]})

    assert sent[0]['alarm']['status'] == 4
    assert 'alarm' not in sent[1]
    p4p.close()


def test_SimplePVAInterface_compute_alarm_defaults_missing_severities(monkeypatch):
    config = {
        'variables': {
            'test:float:AA': {
                'name': 'test:float:AA',
                'proto': 'pva',
                'type': 'scalar',
                'compute_alarm': True,
                'valueAlarm': {
                    'lowAlarmLimit': -5.0,
                    'lowWarningLimit': -2.0,
                    'highWarningLimit': 2.0,
                    'highAlarmLimit': 5.0,
                },
            }
        }
    }
    p4p = SimplePVAInterface(config)
    sent = []

    def fake_put(name, payload):
        sent.append(payload)
        return None

    monkeypatch.setattr(p4p.ctxt, 'put', fake_put)

    p4p.put('test:float:AA', {'value': 3.0})
    p4p.put('test:float:AA', {'value': 6.0})

    assert sent[0]['alarm']['severity'] == 1
    assert sent[0]['alarm']['status'] == 4
    assert sent[1]['alarm']['severity'] == 2
    assert sent[1]['alarm']['status'] == 3
    p4p.close()


def test_SimplePVAInterface_reject_compute_alarm_with_active_false():
    config = {
        'variables': {
            'test:float:AA': {
                'name': 'test:float:AA',
                'proto': 'pva',
                'type': 'scalar',
                'compute_alarm': True,
                'valueAlarm': {
                    'active': False,
                    'lowAlarmLimit': -5.0,
                    'lowWarningLimit': -2.0,
                    'highWarningLimit': 2.0,
                    'highAlarmLimit': 5.0,
                },
            }
        }
    }
    with pytest.raises(
        ValueError, match='compute_alarm=true does not allow valueAlarm.active=false'
    ):
        SimplePVAInterface(config)
