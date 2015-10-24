"""
reddit_info_bot exceptions
"""

class BotException(Exception):
    """Base exception of reddit_info_bot"""

class ConfigurationError(BotException):
    """Indicates missing configuration options
    or an error while parsing a configuration file."""
