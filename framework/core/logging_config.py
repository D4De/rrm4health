"""
Logging Configuration for RRM4Health Framework

This module provides centralized logging configuration.
Import and call setup_logging() at the start of your application.
"""

import logging
import sys
from pathlib import Path


def setup_logging(level=logging.INFO, log_file=None, console_output=True):
    """
    Configure logging for the entire framework.
    
    Args:
        level: Logging level (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR)
               - DEBUG: Detailed information for debugging (status displays, message traffic)
               - INFO: General informational messages (connections, lifecycle events)
               - WARNING: Warning messages (non-critical issues)
               - ERROR: Error messages (failures, exceptions)
        log_file: Optional path to a log file. If None, no file logging is performed.
        console_output: If True, output logs to console (terminal)
    
    Example:
        # For production - show only INFO and above
        setup_logging(level=logging.INFO)
        
        # For debugging - show everything
        setup_logging(level=logging.DEBUG)
        
        # With file output
        setup_logging(level=logging.INFO, log_file="rrm.log")
        
        # Quiet mode - only errors
        setup_logging(level=logging.ERROR)
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, filters control what gets displayed
    
    # Remove any existing handlers
    root_logger.handlers.clear()
    
    # Create formatter with timestamp, logger name, level, and message
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Simplified formatter without timestamp for console (optional)
    console_formatter = logging.Formatter(
        fmt='[%(levelname)s] %(name)s: %(message)s'
    )
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name):
    """
    Get a logger instance for a module.
    
    Args:
        name: Usually __name__ from the calling module
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Predefined logging levels for easy import
LEVEL_DEBUG = logging.DEBUG
LEVEL_INFO = logging.INFO
LEVEL_WARNING = logging.WARNING
LEVEL_ERROR = logging.ERROR
LEVEL_CRITICAL = logging.CRITICAL
