from poly_lithic.src.model_utils.LocalModelGetter import LocalModelGetter


def test_LocalModelGetter():
    model_getter = LocalModelGetter({
        'model_path': 'tests/model/model_definition.py',
        'model_factory_class': 'ModelFactory',
    })
    model = model_getter.get_model()
    input_dict = {'x1': 1.0, 'x2': 2.0}

    for i in range(10):
        input_dict['x1'] = float(i)
        input_dict['x2'] = i * 2.0
        output_dict = model.evaluate(input_dict)
        assert output_dict['y'] == max(input_dict['x1'], input_dict['x2'])
