import cProfile
import pstats
import io
from poly_lithic.src.interfaces import registered_interfaces

SimplePVAInterfaceServer = registered_interfaces['p4p_server']


def profile_get_many(interface, data):
    pr = cProfile.Profile()
    pr.enable()

    # Call the get_many function
    result = interface.get_many(data)

    pr.disable()
    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats()
    print(s.getvalue())

    return result


# Example usage
if __name__ == '__main__':
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

    # add 100 random arrays of len 100
    for i in range(100):
        config['variables']['test_array_{}'.format(i)] = {
            'name': 'test_array_{}'.format(i),
            'proto': 'pva',
            'type': 'waveform',
            'default': list(range(100)),
        }

    interface = SimplePVAInterfaceServer(config)
    data = ['test', 'test_array']
    data.extend(['test_array_{}'.format(i) for i in range(100)])

    # Profile the get_many function
    result = profile_get_many(interface, data)
    # print(result)
