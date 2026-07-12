import re

from app.schemas.imports import DesignationSuggestion, ImportDraft, PlayerDraft, WishDraft


SECTION_MARKERS = {
    "#指定信息": "designations",
    "#玩家信息": "players",
    "#场内点心": "snacks",
    "#其他备注": "other_notes",
}


def parse_group_board(text: str) -> ImportDraft:
    sections: dict[str, list[str]] = {name: [] for name in SECTION_MARKERS.values()}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker = next((value for key, value in SECTION_MARKERS.items() if line.startswith(key)), None)
        if marker:
            current = marker
            continue
        if current:
            sections[current].append(line)

    wishes: list[WishDraft] = []
    suggestions: list[DesignationSuggestion] = []
    unresolved: list[str] = []
    for line in sections["designations"]:
        if "虔诚许愿" in line:
            wish = _parse_wish(line)
            wishes.append(wish) if wish else unresolved.append(line)
        elif "热力榜三" in line:
            suggestion = _parse_top_three(line)
            suggestions.append(suggestion) if suggestion else unresolved.append(line)
        else:
            unresolved.append(line)

    players: list[PlayerDraft] = []
    for line in sections["players"]:
        parsed = _parse_player(line)
        if parsed:
            players.append(parsed)

    notes = _parse_notes(sections["snacks"]) | _parse_notes(sections["other_notes"])
    return ImportDraft(wishes, suggestions, players, notes, unresolved)


def _parse_wish(line: str) -> WishDraft | None:
    match = re.search(r"】-?\s*([^/]+)/([^-（(]+)-([^（(\s]+)\s*(.*)$", line)
    if not match:
        return None
    return WishDraft(
        actor_name=match.group(1).strip(),
        role_name=match.group(2).strip(),
        player_name=match.group(3).strip(),
        raw_note=match.group(4).strip(" ()（）"),
    )


def _parse_top_three(line: str) -> DesignationSuggestion | None:
    match = re.search(r"热力榜三-([^/]+)/([^（(]+)", line)
    if not match:
        return None
    return DesignationSuggestion(
        actor_name=match.group(1).strip(),
        role_name=match.group(2).strip(),
        player_name=None,
        suggested_type="top_three",
        raw_line=line,
    )


def _parse_player(line: str) -> PlayerDraft | None:
    match = re.search(r"【([^】]+)】([^（(：:]+)(?:[（(]([^）)]+)[）)])?[：:]\s*(.+)$", line)
    if not match:
        return None
    return PlayerDraft(
        label=match.group(1).strip(),
        role_name=match.group(2).strip(),
        relation=match.group(3).strip() if match.group(3) else None,
        player_name=match.group(4).strip(),
    )

def _parse_notes(lines: list[str]) -> dict[str, str]:
    notes: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []
    for line in lines:
        if line.endswith("：") or line.endswith(":"):
            if current_key and buffer:
                notes[current_key] = " ".join(buffer).strip()
            current_key = line.rstrip("：:")
            buffer = []
        elif current_key is not None:
            buffer.append(line)
        elif "：" in line or ":" in line:
            key, value = re.split(r"[：:]", line, maxsplit=1)
            current_key = key.strip()
            buffer = [value.strip()]
    if current_key and buffer:
        notes[current_key] = " ".join(buffer).strip()
    return notes
