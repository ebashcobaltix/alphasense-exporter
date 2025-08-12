# logger.py
import logging

# Flag to ensure logging is only configured once
_logging_configured = False

def setup_logging(level='INFO'):
    """Configure logging once for the entire application"""
    global _logging_configured
    
    if _logging_configured:
        return
    
    # Convert string level to logging constant
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    # Clear any existing handlers to prevent duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    _logging_configured = True

def get_logger(name):
    """Get a logger that uses the configured root logger"""
    # Ensure logging is setup with defaults if not already done
    if not _logging_configured:
        setup_logging()
    
    logger = logging.getLogger(name)
    # Don't add handlers - let it use the root logger's configuration
    # Prevent propagation issues by not setting handlers on child loggers
    return logger
