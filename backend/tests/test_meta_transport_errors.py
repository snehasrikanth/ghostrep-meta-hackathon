import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from app.config import Settings
from app.services.meta.errors import MetaTimeout, MetaUnavailable
from app.services.meta.transport import call_with_retries, translate_sdk_error


@pytest.mark.parametrize(
    "error_type,kind,public_type,message",
    [
        (APIConnectionError, "connection", MetaUnavailable, "could not connect to Meta"),
        (APITimeoutError, "timeout", MetaTimeout, "too long to respond"),
    ],
)
def test_connection_failures_and_timeouts_have_distinct_messages(
    error_type, kind, public_type, message
):
    request = httpx.Request("POST", "https://api.meta.ai/v1/chat/completions")
    sdk_error = error_type(request=request)
    mapped = translate_sdk_error(sdk_error)
    assert mapped.kind == kind
    attempts = []

    def fail():
        attempts.append(1)
        raise mapped

    settings = Settings(meta_max_retries=0, meta_retry_sleep=False)
    with pytest.raises(public_type, match=message) as caught:
        call_with_retries(fail, settings, lambda *_: None)
    assert len(attempts) == 1
    assert "retries" not in str(caught.value)
