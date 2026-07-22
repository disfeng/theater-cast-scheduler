from dataclasses import dataclass


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PageWindow:
    limit: int
    offset: int


def page_window(
    *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0, maximum: int = MAX_PAGE_SIZE
) -> PageWindow:
    if limit < 1 or offset < 0 or maximum < 1:
        raise ValueError("pagination_invalid")
    return PageWindow(limit=min(limit, maximum), offset=offset)
