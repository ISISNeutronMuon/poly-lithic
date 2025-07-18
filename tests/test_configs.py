#!/usr/bin/env python3
"""
Script to list all registered models in MLflow
"""

import os
import json
from mlflow import MlflowClient
from poly_lithic.src.logging_utils import get_logger

logger = get_logger()


def load_env_config():
    """Load environment configuration from env.json if it exists"""
    env_file = 'env.json'
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r') as f:
                env_config = json.load(f)

            # Set MLflow environment variables if they exist in config
            if 'MLFLOW_TRACKING_URI' in env_config:
                os.environ['MLFLOW_TRACKING_URI'] = env_config['MLFLOW_TRACKING_URI']
                logger.info(
                    f'Set MLFLOW_TRACKING_URI to: {env_config["MLFLOW_TRACKING_URI"]}'
                )

            if 'MLFLOW_TRACKING_USERNAME' in env_config:
                os.environ['MLFLOW_TRACKING_USERNAME'] = env_config[
                    'MLFLOW_TRACKING_USERNAME'
                ]

            if 'MLFLOW_TRACKING_PASSWORD' in env_config:
                os.environ['MLFLOW_TRACKING_PASSWORD'] = env_config[
                    'MLFLOW_TRACKING_PASSWORD'
                ]

        except Exception as e:
            logger.warning(f'Could not load env.json: {e}')
    else:
        logger.info('No env.json found, using existing environment variables')


def list_registered_models():
    """List all registered models and their versions"""
    try:
        client = MlflowClient()

        # Get all registered models
        registered_models = client.search_registered_models()

        if not registered_models:
            print('No registered models found.')
            return

        print(f'\nFound {len(registered_models)} registered model(s):\n')
        print('-' * 100)

        for model in registered_models:
            print(f'Model Name: {model.name}')
            print(f'Description: {model.description or "No description"}')
            print(f'Tags: {model.tags or "No tags"}')

            # Get model versions
            try:
                versions = client.search_model_versions(f"name='{model.name}'")
                print(f'Versions: {len(versions)}')

                for version in versions:
                    print(f'  - Version {version.version}: {version.current_stage}')
                    print(f'    Source: {version.source}')
                    print(f'    Created: {version.creation_timestamp}')
                    if version.description:
                        print(f'    Description: {version.description}')

            except Exception as e:
                print(f'  Error getting versions: {e}')

            print('-' * 100)

    except Exception as e:
        logger.error(f'Error connecting to MLflow: {e}')
        print(f'Error: {e}')
        print('\nTroubleshooting:')
        print('1. Check if MLflow server is running')
        print('2. Verify MLFLOW_TRACKING_URI is set correctly')
        print('3. Check network connectivity to MLflow server')


def main():
    """Main function"""
    print('MLflow Registered Models Lister')
    print('=' * 50)

    # Load environment configuration
    load_env_config()

    # Show current MLflow configuration
    tracking_uri = os.environ.get('MLFLOW_TRACKING_URI', 'Not set')
    print(f'MLflow Tracking URI: {tracking_uri}')

    # List registered models
    list_registered_models()


if __name__ == '__main__':
    main()
