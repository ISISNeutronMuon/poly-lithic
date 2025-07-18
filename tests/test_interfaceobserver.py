import pytest
import os
import numpy as np
from poly_lithic.src.utils.messaging import Message, InterfaceObserver
from poly_lithic.src.interfaces import registered_interfaces


@pytest.fixture
def p4p_server():
    config = {
        'variables': {
            'test_scalar': {
                'name': 'test_scalar',
                'proto': 'pva',
                'type': 'scalar',
                'default': 0.0,
            },
            'test_array': {
                'name': 'test_array',
                'proto': 'pva',
                'type': 'waveform',
                'default': [1.0, 2.0, 3.0],
            },
        }
    }
    p4p = registered_interfaces['p4p_server'](config)
    yield p4p
    p4p.close()


@pytest.fixture
def interface_observer(p4p_server):
    return InterfaceObserver(p4p_server, 'next_step')


def test_interface_observer_put(interface_observer):
    # Test putting a scalar value
    message = Message(
        topic='interface', source='model', value={'test_scalar': {'value': 5.0}}
    )

    # Set environment variable for publishing
    os.environ['PUBLISH'] = 'True'

    # Test put method
    interface_observer.put(message)

    # Verify value was set
    name, value_dict = interface_observer.interface.get('test_scalar')
    assert value_dict['value'] == 5.0
    assert name == 'test_scalar'

    message = Message(
        topic='interface', source='model', value={'test_scalar': {'value': 6.0}}
    )

    interface_observer.put(message)

    # Verify value was set
    name, value_dict = interface_observer.interface.get('test_scalar')
    assert value_dict['value'] == 6.0
    assert name == 'test_scalar'


def test_interface_observer_put_many(interface_observer):
    # Test putting multiple values
    values = {
        'test_scalar': {'value': 7.0},
        'test_array': {'value': np.array([4.0, 5.0, 6.0])},
    }

    message = Message(
        topic='interface', source='model', key='batch_update', value=values
    )

    os.environ['PUBLISH'] = 'True'

    interface_observer.put(message)

    # Verify values were set
    name, scalar_value = interface_observer.interface.get('test_scalar')
    assert scalar_value['value'] == 7.0

    name, array_value = interface_observer.interface.get('test_array')
    np.testing.assert_array_equal(array_value['value'], np.array([4.0, 5.0, 6.0]))


def test_interface_observer_get(interface_observer):
    # Set a value first
    interface_observer.interface.put('test_scalar', 3.0)
    os.environ['PUBLISH'] = 'True'
    # Test get method
    message = Message(
        topic='interface', source='request', value={'test_scalar': {'value': None}}
    )

    result = interface_observer.get(message)[0]

    assert result.topic == 'next_step'
    assert result.keys == ['test_scalar']
    assert result.value['test_scalar']['value'] == 3.0


def test_interface_observer_get_all(interface_observer):
    # Set some values first
    values = {
        'test_scalar': {'value': 9.0},
        'test_array': {'value': np.array([7.0, 8.0, 9.0])},
    }
    os.environ['PUBLISH'] = 'True'
    interface_observer.interface.put_many(values)

    # Test get_all method
    result = interface_observer.get_all()

    assert len(result) == 1
    assert result[0].topic == 'next_step'
    assert result[0].value['test_scalar'] == {'value': 9.0}

    np.testing.assert_array_equal(
        result[0].value['test_array']['value'], np.array([7.0, 8.0, 9.0])
    )


def test_interface_observer_update_no_publish(interface_observer):
    # Test update method when PUBLISH is False
    os.environ['PUBLISH'] = 'False'

    message = Message(
        topic='interface', source='model', value={'test_scalar': {'value': 10.0}}
    )

    # Should not update when PUBLISH is False
    interface_observer.update(message)

    name, value_dict = interface_observer.interface.get('test_scalar')
    assert value_dict['value'] == 0.0  # Should not have updated


@pytest.mark.asyncio
async def test_interface_observer_async_updates(interface_observer):
    """Test that observer can handle rapid updates"""
    os.environ['PUBLISH'] = 'True'

    import asyncio

    async def send_updates():
        for i in range(5):
            message = Message(
                topic='interface',
                source='model',
                value={'test_scalar': {'value': float(i)}},
            )
            interface_observer.update(message)
            await asyncio.sleep(0.1)

    await send_updates()

    name, value_dict = interface_observer.interface.get('test_scalar')
    assert value_dict['value'] == 4.0  # Should have last value
