import math

import numpy as np
from poly_lithic.src.logging_utils.make_logger import get_logger
from poly_lithic.src.transformers.BaseTransformers import (
    CAImageTransfomer,
    PassThroughTransformer,
    SimpleTransformer,
)
from poly_lithic.src.transformers.CompoundTransformer import CompoundTransformer

logger = get_logger()

config1 = {
    'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
    'symbols': ['A1', 'B1'],
}


def test_simple_transformer():
    st = SimpleTransformer(config1)

    print(st)
    print(st.pv_mapping)

    st.handler('A1', {'value': 1})
    st.handler('B1', {'value': 2})

    assert st.updated is True
    print(st.latest_transformed)

    assert st.latest_transformed['x2'] == 1 + 2
    assert st.latest_transformed['x1'] == 1


# more complex configuration
config2 = {
    'variables': {
        'x2': {'formula': 'A1**2'},
        'x1': {'formula': 'A1'},
        'x3': {'formula': 'sin(A1) + cos(B1)'},
    },
    'symbols': ['A1', 'B1'],
}


def test_simple_transformer_complex():
    st = SimpleTransformer(config2)

    print(st)
    print(st.pv_mapping)

    st.handler('A1', {'value': 1})
    st.handler('B1', {'value': 2})

    assert st.updated is True

    assert st.latest_transformed['x2'] == 1**2
    assert st.latest_transformed['x1'] == 1
    assert st.latest_transformed['x3'] == math.sin(1) + math.cos(2)


config2a = {
    'variables': {
        'x2': {'formula': 'A1*B1'},
        'x1': {'formula': 'A1'},
        'x3': {'formula': 'B1 + A1'},
        'x4': {'formula': 'C1*B1'},
    },
    'symbols': ['A1', 'B1', 'C1'],
}

# removed for now
# def test_simple_transformer_complex_array_in():
#     st = SimpleTransformer(config2a)

#     print(st)
#     print(st.pv_mapping)

#     st.handler('A1', {'value': np.array([1, 2, 3])})
#     st.handler('B1', {'value': np.array([4, 5, 6])})
#     st.handler('C1', {'value': np.array([4, 5, 6])})

#     assert st.updated
#     expected_result = np.outer(np.array([1, 2, 3]), np.array([4, 5, 6]))
#     np.testing.assert_array_equal(st.latest_transformed['x2'], expected_result)
#     np.testing.assert_array_equal(st.latest_transformed['x1'], np.array([1, 2, 3]))
#     np.testing.assert_array_equal(
#         st.latest_transformed['x3'], np.array([4, 5, 6]) + np.array([1, 2, 3])
#     )
#     np.testing.assert_array_equal(st.latest_transformed['x4'], 7 * np.array([4, 5, 6]))


config3 = {
    'variables': {
        'img_1': {
            'img_ch': 'MY_TEST_CA',
            'img_x_ch': 'MY_TEST_CA_X',
            'img_y_ch': 'MY_TEST_CA_Y',
        },
        'img_2': {
            'img_ch': 'MY_TEST_C2',
            'img_x_ch': 'MY_TEST_CA_X2',
            'img_y_ch': 'MY_TEST_CA_Y2',
        },
    },
}
# maybe we need a folding direction in the config


def test_ca_image_transformer():
    img_transformer = CAImageTransfomer(config3)
    print(img_transformer)
    # simple list arry
    img_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    img_1_x = 3
    img_1_y = 3
    # 3x3 image

    img_2 = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    img_2_x = 4  # columns
    img_2_y = 3  # rows
    # numpy array 3x4 image

    # both should return the np.array with shape (3, 3) and (3, 4) respectively
    img_transformer.handler('MY_TEST_CA_X', {'value': img_1_x})
    img_transformer.handler('MY_TEST_CA_Y', {'value': img_1_y})
    img_transformer.handler('MY_TEST_CA', {'value': img_1})

    img_transformer.handler('MY_TEST_CA_X2', {'value': img_2_x})
    img_transformer.handler('MY_TEST_CA_Y2', {'value': img_2_y})
    img_transformer.handler('MY_TEST_C2', {'value': img_2})

    assert img_transformer.updated is True

    assert img_transformer.latest_transformed['img_1'].shape == (3, 3)
    assert img_transformer.latest_transformed['img_2'].shape == (3, 4)

    # check positions of al 4 corners in each image
    assert img_transformer.latest_transformed['img_1'][0, 0] == 1
    assert img_transformer.latest_transformed['img_1'][0, 2] == 3
    assert img_transformer.latest_transformed['img_1'][2, 0] == 7
    assert img_transformer.latest_transformed['img_1'][2, 2] == 9

    assert img_transformer.latest_transformed['img_2'][0, 0] == 1
    assert img_transformer.latest_transformed['img_2'][0, 3] == 4
    assert img_transformer.latest_transformed['img_2'][2, 0] == 9
    assert img_transformer.latest_transformed['img_2'][2, 3] == 12


config4 = {
    'transformers': {
        'transformer_1': {'type': 'SimpleTransformer', 'config': config2},
        'transformer_2': {'type': 'CAImageTransfomer', 'config': config3},
    }
}


def test_compound_transformer():
    ct = CompoundTransformer(config4)
    assert len(ct.transformers) == 2

    img_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    img_1_x = 3
    img_1_y = 3
    # 3x3 image

    img_2 = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    img_2_x = 4
    img_2_y = 3
    # numpy array 3x4 image

    ct.handler('A1', {'value': 1})
    ct.handler('B1', {'value': 2})
    ct.handler('MY_TEST_CA_X', {'value': img_1_x})
    ct.handler('MY_TEST_CA_Y', {'value': img_1_y})
    ct.handler('MY_TEST_CA', {'value': img_1})
    ct.handler('MY_TEST_CA_X2', {'value': img_2_x})
    ct.handler('MY_TEST_CA_Y2', {'value': img_2_y})
    ct.handler('MY_TEST_C2', {'value': img_2})

    assert ct.updated is True

    assert ct.latest_transformed['img_1'].shape == (3, 3)
    assert ct.latest_transformed['img_2'].shape == (3, 4)

    # check positions of al 4 corners in each image
    assert ct.latest_transformed['img_1'][0, 0] == 1
    assert ct.latest_transformed['img_1'][0, 2] == 3
    assert ct.latest_transformed['img_1'][2, 0] == 7
    assert ct.latest_transformed['img_1'][2, 2] == 9

    assert ct.latest_transformed['img_2'][0, 0] == 1
    assert ct.latest_transformed['img_2'][0, 3] == 4
    assert ct.latest_transformed['img_2'][2, 0] == 9
    assert ct.latest_transformed['img_2'][2, 3] == 12

    assert ct.latest_transformed['x2'] == 1**2
    assert ct.latest_transformed['x1'] == 1
    assert ct.latest_transformed['x3'] == math.sin(1) + math.cos(2)

    print(ct.latest_transformed)


config5 = {
    'variables': {
        'IMG1': 'input_image',
        'var1': 'input_var1',
    }
}

# we just relabel the input variables


def test_pass_through_transformer():
    pt = PassThroughTransformer(config5)
    assert pt.updated is False
    pt.handler('input_image', {'value': np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])})
    pt.handler('input_var1', {'value': 1})
    assert pt.updated is True
    assert pt.latest_transformed['IMG1'].shape == (3, 3)
    assert pt.latest_transformed['var1'] == 1
    print(pt.latest_transformed)
