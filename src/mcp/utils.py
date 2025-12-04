"""Utility functions for MCP server."""

import re
import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)


def validate_url(url: str) -> bool:
    """
    Validate a URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def validate_arguments(arguments: Dict[str, Any], required: list, schema: Optional[Dict] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate tool arguments.
    
    Args:
        arguments: Arguments to validate
        required: List of required argument names
        schema: Optional JSON schema for validation
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    for field in required:
        if field not in arguments:
            return False, f"Missing required argument: {field}"
        
        if arguments[field] is None:
            return False, f"Required argument '{field}' cannot be None"
    
    # Validate URLs if present
    for field in ["url", "endpoint"]:
        if field in arguments:
            url = arguments[field]
            if not isinstance(url, str):
                return False, f"'{field}' must be a string"
            if not validate_url(url):
                return False, f"Invalid URL format: {url}"
    
    return True, None


def with_timeout(timeout: float):
    """
    Decorator to add timeout to async functions.
    
    Args:
        timeout: Timeout in seconds
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"Function {func.__name__} timed out after {timeout}s")
                raise TimeoutError(f"Operation timed out after {timeout} seconds")
        return wrapper
    return decorator


def with_retry(max_retries: int = 3, delay: float = 1.0, exceptions: tuple = (Exception,)):
    """
    Decorator to add retry logic to async functions.
    
    Args:
        max_retries: Maximum number of retries
        delay: Delay between retries in seconds
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_retries} attempts failed for {func.__name__}")
            raise last_exception
        return wrapper
    return decorator


def safe_get(dictionary: Dict, *keys, default: Any = None) -> Any:
    """
    Safely get nested dictionary values.
    
    Args:
        dictionary: Dictionary to search
        keys: Keys to traverse
        default: Default value if key not found
        
    Returns:
        Value or default
    """
    result = dictionary
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    return result

