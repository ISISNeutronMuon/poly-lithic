import logging

import colorlog


def make_logger(name='model_manager', level=logging.INFO):
    logger = colorlog.getLogger(name)
    handler = colorlog.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s[%(filename)s:%(lineno)s:%(funcName)s] %(levelname)s: %(message)s',
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%',
    )
    handler.setFormatter(formatter)

    # check if logger has handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = (
        False  # Prevent the log messages from being duplicated in the python consoles
    )

    return logger


def get_logger():
    logger = logging.getLogger('model_manager')
    return logger


def reset_logging():
    # Remove all handlers from the root logger
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Reset the logging configuration
    logging.basicConfig(level=logging.ERROR)
