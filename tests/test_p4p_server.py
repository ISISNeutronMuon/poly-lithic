# from poly_lithic.src.interfaces import SimplePVAInterfaceServer
# from poly_lithic.src.transformers import PassThroughTransformer, CompoundTransformer
import numpy as np
import pytest
from poly_lithic.src.interfaces import registered_interfaces
from poly_lithic.src.logging_utils.make_logger import make_logger
from poly_lithic.src.transformers import registered_transformers

SimplePVAInterfaceServer = registered_interfaces['p4p_server']
CompoundTransformer = registered_transformers['CompoundTransformer']

logger = make_logger('model_manager')


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
