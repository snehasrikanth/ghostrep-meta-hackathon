"""Failures from a Meta provider. None of these are reported as a successful model result."""


class MetaError(RuntimeError):
    pass


class MetaRejected(MetaError):
    """The provider answered, but the payload failed GhostRep's checks. Do not retry."""


class MetaRateLimited(MetaError):
    pass


class MetaTimeout(MetaError):
    pass


class MetaUnavailable(MetaError):
    """The provider failed after the allowed retries."""


class TransientMetaError(MetaError):
    def __init__(self, kind: str, message: str = ""):
        self.kind = kind
        super().__init__(message or kind)
