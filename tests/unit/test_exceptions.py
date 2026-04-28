from ah_research.exceptions import (
    AHResearchError,
    DataIntegrityError,
    InsufficientData,
    LeakageDetected,
    ResearchError,
    SourceAuthError,
    SourceDataError,
    SourceError,
    SourceRateLimit,
    SourceSchemaError,
    SourceUnavailable,
    UnsupportedOperation,
    UserInputError,
)


def test_all_errors_inherit_from_root():
    for cls in (
        SourceError,
        SourceRateLimit,
        SourceUnavailable,
        SourceSchemaError,
        SourceAuthError,
        SourceDataError,
        DataIntegrityError,
        UserInputError,
        ResearchError,
        LeakageDetected,
        UnsupportedOperation,
        InsufficientData,
    ):
        assert issubclass(cls, AHResearchError)


def test_source_sub_errors_inherit_from_source_error():
    for cls in (
        SourceRateLimit,
        SourceUnavailable,
        SourceSchemaError,
        SourceAuthError,
        SourceDataError,
    ):
        assert issubclass(cls, SourceError)


def test_research_sub_errors_inherit_from_research_error():
    for cls in (LeakageDetected, UnsupportedOperation, InsufficientData):
        assert issubclass(cls, ResearchError)


def test_source_rate_limit_is_retryable_marker():
    assert SourceRateLimit.retryable is True
    assert SourceUnavailable.retryable is True
    assert SourceSchemaError.retryable is False
    assert SourceAuthError.retryable is False
