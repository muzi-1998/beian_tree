"""D3 configuration and threshold-contract exceptions."""


class D3Error(Exception):
    """Base class for D3 contract failures."""


class ConfigValidationError(D3Error):
    """Raised when a D3 configuration or threshold library is invalid."""


class TailRateContractViolation(D3Error):
    """Raised when a diagnostic tail threshold has an unapproved source."""
