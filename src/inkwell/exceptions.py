"""Exception hierarchy for Inkwell."""


class InkwellError(Exception):
    """Base exception for all Inkwell errors."""


class NetworkError(InkwellError):
    """Error during HTTP requests."""


class RateLimitError(NetworkError):
    """Rate limit hit on a site."""


class AuthenticationError(NetworkError):
    """Authentication required or failed."""


class ParseError(InkwellError):
    """Error parsing page content."""


class UnsupportedSiteError(InkwellError):
    """URL does not match any registered site handler."""


class EpubBuildError(InkwellError):
    """Error building the EPUB file."""


class ConfigError(InkwellError):
    """Error in configuration."""


class CacheError(InkwellError):
    """Error reading or writing download cache."""
