import pytest

from computer_agent.computer.actions import (
    DEMO_ROOT,
    UnsafeNavigationError,
    _ensure_demo_destination,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "file:///C:/Users/Public/other-page.html",
        "file://server/share/page.html",
        (DEMO_ROOT / ".." / "outside-page.html").as_uri(),
    ],
)
def test_local_runtime_rejects_out_of_scope_destinations(url: str) -> None:
    with pytest.raises(UnsafeNavigationError):
        _ensure_demo_destination(url)
