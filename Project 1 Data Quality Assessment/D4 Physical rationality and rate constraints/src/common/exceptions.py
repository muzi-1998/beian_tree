"""D4 configuration and threshold-contract exceptions."""


class D4Error(Exception):
    """Base class for D4 contract failures."""


class ConfigValidationError(D4Error):
    """Raised when a D4 configuration or threshold library is invalid."""


class TailRateContractViolation(D4Error):
    """Raised when a diagnostic tail threshold has an unapproved source."""
