import pytest

from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PageWindow, page_window


def test_page_window_uses_bounded_defaults():
    assert DEFAULT_PAGE_SIZE == 50
    assert MAX_PAGE_SIZE == 100
    assert page_window() == PageWindow(limit=50, offset=0)


def test_page_window_caps_requested_size():
    assert page_window(limit=999, offset=25) == PageWindow(limit=100, offset=25)


@pytest.mark.parametrize("limit,offset", [(0, 0), (-1, 0), (10, -1)])
def test_page_window_rejects_invalid_values(limit: int, offset: int):
    with pytest.raises(ValueError, match="pagination_invalid"):
        page_window(limit=limit, offset=offset)
