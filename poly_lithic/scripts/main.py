def main():
    import asyncio
    import logging
    import os
    from poly_lithic.src.cli import model_main, setup
    from poly_lithic.src.logging_utils import make_logger, reset_logging

    logger = make_logger('model_manager')
    logger.info('Starting model manager')

    (args, config, broker) = setup()
    print('resetting logging...')
    reset_logging()

    if os.environ.get('DEBUG') == 'True':
        logger = make_logger('model_manager', level=logging.DEBUG)
    else:
        logger = make_logger('model_manager')

    asyncio.run(model_main(args, config, broker))


if __name__ == '__main__':
    main()
