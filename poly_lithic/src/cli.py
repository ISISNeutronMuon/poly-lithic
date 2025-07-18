import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback

from poly_lithic.src.config import ConfigParser
from poly_lithic.src.logging_utils import get_logger, make_logger

from poly_lithic.src.utils.builder import Builder

from poly_lithic._version import __version__

logger = get_logger()

init_time = time.time()

# if file build-info exists, set the environment variables
if os.path.exists('build-info.json'):
    with open('build-info.json') as stream:
        data = json.load(stream)
    for key, value in data.items():
        os.environ[key] = value

print('=' * 120)
# print(f"Commit head: {os.environ['vcs-ref']}")
# print(f"Build time: {os.environ['build-date']}")
print(f'Version: {__version__}')
print('=' * 120 + '\n')


def initailize_config(config_path):
    """Initialize the configuration."""
    try:
        config_parser = ConfigParser(config_path)
        return config_parser.parse()
    except Exception as e:
        logger.error(f'Error initializing configuration: {e}')
        raise e


def env_config(env_config):
    """Set the environment variables."""
    logger.debug(f'Setting environment variables from: {env_config}')
    try:
        # load json
        with open(env_config) as stream:
            data = json.load(stream)
        for key, value in data.items():
            os.environ[key] = value
    except Exception as e:
        logger.error(f'Error setting environment variables: {e}')
        raise e


def setup():
    """Setup the model manager."""
    parser = argparse.ArgumentParser(description='Model Manager CLI')

    parser.add_argument(
        '-d',
        '--debug',
        help='Debug mode',
        required=False,
        default=False,
        action='store_true',
    )

    parser.add_argument(
        '-c', '--config', help='Path to the configuration file', required=False
    )
    parser.add_argument(
        '-g',
        '--model_getter',
        help='Method to obtain the model',
        choices=['mlflow', 'local'],
        default='mlflow',
    )
    # parser.add_argument(
    #     "-n",
    #     "--model_name",
    #     required=False,
    #     help="Name of the model to be loaded from mlflow",
    # )
    parser.add_argument(
        '-v',
        '--version',
        help='Print Version and exit',
        required=False,
        default=False,
        action='store_true',
    )
    parser.add_argument(
        '-r',
        '--reqirements',
        help='reqirements install only, if True requirements.txt is obtained from the model and installed, program then exits',
        required=False,
        default=False,
        action='store_true',
    )
    # env
    parser.add_argument(
        '-e',
        '--env',
        help='Path to the environment configuration file, json format',
        required=False,
    )

    parser.add_argument(
        '-o',
        '--one_shot',
        help='One shot mode, run once and exit, helpful for debugging',
        required=False,
        default=False,
        action='store_true',
    )

    # publish
    parser.add_argument(
        '-p',
        '--publish',
        help='Publish data to system, if True data is published, otherwise the step is skipped',
        required=False,
        default=False,
        action='store_true',
    )

    # version print and exit
    # parser.add_argument(
    #     '-v',
    #     '--version',
    #     help='Print version and exit',
    #     required=False,
    #     default=False,
    #     action='store_true',
    # )

    args = parser.parse_args()

    if args.version:
        os.environ['version'] = __version__
        print(f'Ploy-Lithic version: {os.environ["version"]}')
        sys.exit(0)

    # change logger level
    if args.debug:
        print('Debug mode')
        logger = make_logger(level=logging.DEBUG)
        os.environ['DEBUG'] = 'True'
    else:
        print('Info mode')
        logger = make_logger(level=logging.INFO)
        os.environ['DEBUG'] = 'False'

    logger.info('Model Manager CLI')

    logger.debug(f'Arguments: {args}')

    if args.publish:
        logger.warning('Publishing data to system')
        os.environ['PUBLISH'] = 'True'
    else:
        logger.warning('Not publishing data to system, to publish use -p or --publish')
        os.environ['PUBLISH'] = 'False'

    # env useful when running in windows
    if args.env:
        env_config(args.env)

    if not args.config:
        logger.info(
            'No configuration file provided, getting config from model artifacts'
        )
        # check if os.environ["MODEL_CONFIG_FILE"] exists
        if os.environ['MODEL_CONFIG_FILE']:
            builder = Builder(args.config)
        else:
            raise Exception(
                'No configuration file provided, this should be done via command -c line or environment variable MODEL_CONFIG_FILE'
            )
    else:
        logger.info(f'Configuration file provided: {args.config}')
        builder = Builder(args.config)

    broker = builder.build()

    return (
        args,
        builder.config,
        broker,
    )


async def model_main(args, config, broker):
    """Main."""
    # monitor and send to transformer handle
    # reintialise logger to get the correct logger and clear any previous handlers
    # print("model_main")

    logger = get_logger()
    logger.info('Starting model manager')

    time.time()
    os.environ['PUBLISH'] = str(args.publish)
    try:
        if config.deployment.type == 'continuous':
            time_start = time.time()
            while True:
                if time.time() - time_start > config.deployment.rate:
                    time_start = time.time()
                    broker.get_all()
                else:
                    if len(broker.queue) > 0:
                        broker.parse_queue()

                if len(broker.queue) > 0:
                    broker.parse_queue()
                    if args.one_shot:
                        logger.info('One shot mode, exiting')
                        break

                await asyncio.sleep(0.01)  # sleep for 10ms

        else:
            raise Exception('Deployment type not supported')
    except Exception as e:
        logger.error(f'Error monitoring: {traceback.format_exc()}')
        raise e
    finally:
        logger.info('Exiting')
        sys.exit(0)
