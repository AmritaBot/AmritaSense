class MatcherException(Exception):
    """Base exception for Matcher."""


class CancelException(MatcherException):
    pass


class PassException(MatcherException):
    pass
