class ParseError(ValueError):
    """Raised when a payload cannot be parsed safely. The message is safe to surface."""
