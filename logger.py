# logger.py
import logging

def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

def setup_logging(level=logging.INFO):
    logging.basicConfig(level=level, format='[%(asctime)s] %(levelname)s - %(message)s')
