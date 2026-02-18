# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation, Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

# from poly_lithic.src.interfaces import SimplePVAInterfaceServer
# from poly_lithic.src.transformers import PassThroughTransformer, CompoundTransformer
import socket

import numpy as np
import pytest
from poly_lithic.src.interfaces import registered_interfaces
from poly_lithic.src.logging_utils.make_logger import make_logger
from poly_lithic.src.transformers import registered_transformers

SimplePVAInterfaceServer = registered_interfaces['p4p_server']
SimplePVAInterface = registered_interfaces['p4p']
CompoundTransformer = registered_transformers['CompoundTransformer']

logger = make_logger('model_manager')


def _get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_SimplePVAInterfaceServer_init():
    config = {'variables': {'test': {'name': 'test', 'proto': 'pva'}}}
    logger.info('Testing SimplePVAInterfaceServer init')
    p4p = SimplePVAInterfaceServer(config)
    assert p4p.shared_pvs['test'].isOpen()
    p4p.close()


def test_SimplePVAInterfaceServer_put_and_get():
    config = {'variables': {'test': {'name': 'test', 'proto': 'pva'}}}
    logger.info('Testing SimplePVAInterfaceServer put')
    p4p = SimplePVAInterfaceServer(config)
    assert p4p.shared_pvs['test'].isOpen()
    p4p.put('test', 1)
    name, value_dict = p4p.get('test')
    print(name, value_dict)
    assert value_dict['value'] == 1
    assert name == 'test'
    p4p.close()


def test_SimplePVAInterfaceServer_put_and_get_image():
    config = {
        'variables': {
            'test': {
                'name': 'test',
                'proto': 'pva',
                'type': 'image',
                'image_size': {'x': 10, 'y': 10},
            }
        }
    }
    p4p = SimplePVAInterfaceServer(config)

    arry = np.ones((10, 10))

    p4p.put('test', arry)
    name, value_dict = p4p.get('test')
    print(name, value_dict)
    print(value_dict['value'], type(value_dict['value']))
    assert value_dict['value'][0][0] == arry[0][0]
    assert value_dict['value'].shape == arry.shape
    assert name == 'test'
    p4p.close()


def test_SimplePVAInterface_put_and_get_array():
    config = {
        'variables': {
            'test:array_l:AA': {
                'name': 'test:array_l:AA',
                'proto': 'pva',
                'type': 'waveform',
            }
        }
    }
    p4p = SimplePVAInterfaceServer(config)

    arry = np.random.rand(10)
    p4p.put('test:array_l:AA', arry.tolist())

    name, array_get = p4p.get('test:array_l:AA')
    print(array_get['value'])
    assert type(array_get['value']) == np.ndarray

    name, array_get = p4p.get('test:array_l:AA')
    print(array_get)
    np.testing.assert_array_equal(array_get['value'], arry)

    p4p.close()


# more of an integration test than a unit test
def test_p4p_as_image_input():
    config = {
        'variables': {
            'test': {
                'name': 'test',
                'proto': 'pva',
                'type': 'image',
                'image_size': {'x': 10, 'y': 10},
            }
        }
    }
    config_pt = {
        'variables': {
            'IMG1': 'test',
        }
    }
    config_compound = {
        'transformers': {
            'transformer_1': {'type': 'PassThroughTransformer', 'config': config_pt},
        }
    }

    p4p = SimplePVAInterfaceServer(config)
    pt = CompoundTransformer(config_compound)

    p4p.put('test', np.ones((10, 10)))
    name, value_dict = p4p.get('test')
    pt.handler('test', value_dict)
    assert pt.updated is True
    assert pt.latest_transformed['IMG1'].shape == (10, 10)
    p4p.close()


def test_SimplePVAInterfaceServer_put_and_get_unknown_type():
    config = {
        'variables': {
            'test': {
                'name': 'test',
                'proto': 'pva',
                'type': 'unknown',
            }
        }
    }
    with pytest.raises(TypeError) as e:
        p4p_server = SimplePVAInterfaceServer(config)
        assert 'Unknown PV type' in str(e)
        p4p_server.close()


def test_SimplePVAInterfaceServer_put_and_get_scalar():
    config = {
        'variables': {
            'test': {
                'name': 'test',
                'proto': 'pva',
                'type': 'scalar',
            }
        }
    }
    p4p = SimplePVAInterfaceServer(config)

    assert p4p.shared_pvs['test'].isOpen()

    val = 5
    p4p.put('test', val)
    name, value_dict = p4p.get('test')
    print(name, value_dict)
    print(value_dict['value'], type(value_dict['value']))
    assert value_dict['value'] == val
    assert name == 'test'
    p4p.close()


def test_initialise_with_defaults():
    config = {
        'variables': {
            'test': {
                'name': 'test',
                'proto': 'pva',
                'default': 5,
            },
            'test_array': {
                'name': 'test_array',
                'proto': 'pva',
                'type': 'waveform',
                'default': [1, 2, 3],
            },
        }
    }

    p4p = SimplePVAInterfaceServer(config)
    assert p4p.shared_pvs['test'].isOpen()
    assert p4p.shared_pvs['test_array'].isOpen()

    assert p4p.shared_pvs['test'].current().raw.value == 5
    assert p4p.shared_pvs['test_array'].current().raw.value[0] == 1
    assert p4p.shared_pvs['test_array'].current().raw.value[1] == 2
    assert p4p.shared_pvs['test_array'].current().raw.value[2] == 3
    assert isinstance(p4p.shared_pvs['test_array'].current().raw.value, np.ndarray)
    p4p.close()


def test_scalar_compute_alarm_on_server():
    config = {
        'variables': {
            'test': {
                'name': 'test',
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
    p4p = SimplePVAInterfaceServer(config)

    p4p.put('test', 6.0)
    alarm = p4p.shared_pvs['test'].current().raw.alarm
    assert alarm.severity == 2
    assert alarm.status == 3
    assert alarm.message == 'HIHI'

    p4p.put('test', -3.0)
    alarm = p4p.shared_pvs['test'].current().raw.alarm
    assert alarm.severity == 1
    assert alarm.status == 6
    assert alarm.message == 'LOW'

    p4p.put('test', 0.0)
    alarm = p4p.shared_pvs['test'].current().raw.alarm
    assert alarm.severity == 0
    assert alarm.status == 0
    assert alarm.message == ''
    p4p.close()


def test_non_scalar_manual_alarm_passthrough_on_server():
    config = {
        'variables': {
            'test_array': {
                'name': 'test_array',
                'proto': 'pva',
                'type': 'waveform',
                'default': [0.0, 0.0, 0.0],
            }
        }
    }
    p4p = SimplePVAInterfaceServer(config)
    payload = {
        'value': [1.0, 2.0, 3.0],
        'alarm': {'severity': 1, 'status': 4, 'message': 'HIGH'},
    }
    p4p.put('test_array', payload)

    current = p4p.shared_pvs['test_array'].current().raw
    np.testing.assert_array_equal(current.value, np.array([1.0, 2.0, 3.0]))
    assert current.alarm.severity == 1
    assert current.alarm.status == 4
    assert current.alarm.message == 'HIGH'
    p4p.close()


def test_non_scalar_without_explicit_alarm_does_not_compute():
    config = {
        'variables': {
            'test_array': {
                'name': 'test_array',
                'proto': 'pva',
                'type': 'waveform',
                'default': [0.0, 0.0, 0.0],
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
    p4p = SimplePVAInterfaceServer(config)
    p4p.put('test_array', [10.0, 11.0, 12.0])
    alarm = p4p.shared_pvs['test_array'].current().raw.alarm
    assert alarm.severity == 0
    assert alarm.status == 0
    assert alarm.message == ''
    p4p.close()


def test_reject_compute_alarm_on_non_scalar_server():
    config = {
        'variables': {
            'test_array': {
                'name': 'test_array',
                'proto': 'pva',
                'type': 'waveform',
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
        SimplePVAInterfaceServer(config)


def test_client_scalar_compute_alarm_to_server(monkeypatch):
    port = _get_free_port()
    server_config = {
        'port': port,
        'variables': {
            'test': {
                'name': 'test',
                'proto': 'pva',
                'type': 'scalar',
            }
        },
    }
    client_config = {
        'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}',
        'variables': {
            'test': {
                'name': 'test',
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
        },
    }

    monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

    server = SimplePVAInterfaceServer(server_config)
    client = SimplePVAInterface(client_config)
    try:
        client.put('test', {'value': 6.0})
        alarm = server.shared_pvs['test'].current().raw.alarm
        assert alarm.severity == 2
        assert alarm.status == 3
        assert alarm.message == 'HIHI'
    finally:
        client.close()
        server.close()


def test_scalar_compute_alarm_defaults_missing_severities():
    config = {
        'variables': {
            'test': {
                'name': 'test',
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
    p4p = SimplePVAInterfaceServer(config)
    try:
        # HIGH band defaults to MINOR(1)
        p4p.put('test', 3.0)
        alarm = p4p.shared_pvs['test'].current().raw.alarm
        assert alarm.severity == 1
        assert alarm.status == 4
        assert alarm.message == 'HIGH'

        # HIHI band defaults to MAJOR(2)
        p4p.put('test', 6.0)
        alarm = p4p.shared_pvs['test'].current().raw.alarm
        assert alarm.severity == 2
        assert alarm.status == 3
        assert alarm.message == 'HIHI'
    finally:
        p4p.close()


def test_reject_server_compute_alarm_with_active_false():
    config = {
        'variables': {
            'test': {
                'name': 'test',
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
        SimplePVAInterfaceServer(config)
