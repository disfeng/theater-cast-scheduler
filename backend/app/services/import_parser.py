import re

from app.schemas.imports import DesignationSuggestion, ImportDraft, PlayerDraft, WishDraft
from app.schemas.performance_boards import ParsedPerformancePlayer


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
        marker = next(
            (value for key, value in SECTION_MARKERS.items() if line.startswith(key)), None
        )
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
    if match:
        return WishDraft(
            actor_name=match.group(1).strip(),
            role_name=match.group(2).strip(),
            player_name=match.group(3).strip(),
            raw_note=match.group(4).strip(" ()（）"),
            raw_line=line,
        )
    parenthesized = re.search(r"】\s*-?\s*([^/]+)/([^（(]+)[（(]([^，,）)]+)[，,]\s*(.*?)[）)]\s*$", line)
    if not parenthesized:
        return None
    return WishDraft(
        actor_name=parenthesized.group(1).strip(),
        role_name=parenthesized.group(2).strip(),
        player_name=parenthesized.group(3).strip(),
        raw_note=parenthesized.group(4).strip(),
        raw_line=line,
    )


def _parse_top_three(line: str) -> DesignationSuggestion | None:
    match = re.search(r"热力榜三-([^/]+)/([^（(]+)", line)
    if not match:
        return None
    owner_match = re.search(r"[（(][^）)]*?-([^）)]+)[）)]\s*$", line)
    return DesignationSuggestion(
        actor_name=match.group(1).strip(),
        role_name=match.group(2).strip(),
        player_name=owner_match.group(1).strip() if owner_match else None,
        suggested_type="top_three",
        raw_line=line,
    )


def _parse_player(line: str) -> PlayerDraft | None:
    parsed = parse_player_registration(line)
    if parsed is None:
        return None
    return PlayerDraft(
        label=parsed.player_character_name,
        role_name=parsed.paired_role_name,
        relation=parsed.relation_label,
        player_name=parsed.player_name,
    )


def parse_player_registration(line: str) -> ParsedPerformancePlayer | None:
    match = re.fullmatch(
        r"\s*【([^】]+)】([^（(：:]+)(?:[（(]([^）)]+)[）)])?[：:]\s*(.+?)\s*",
        line,
    )
    if not match:
        return None
    player_name = match.group(4).strip()
    theater_visit_ordinal = character_visit_ordinal = None
    suffix = re.fullmatch(r"(.+)-(\d+)-(\d+)", player_name)
    if suffix:
        player_name = suffix.group(1).strip()
        theater_visit_ordinal = int(suffix.group(2))
        character_visit_ordinal = int(suffix.group(3))
    return ParsedPerformancePlayer(
        player_name=player_name,
        player_character_name=match.group(1).strip(),
        paired_role_name=match.group(2).strip(),
        relation_label=match.group(3).strip() if match.group(3) else None,
        theater_visit_ordinal=theater_visit_ordinal,
        character_visit_ordinal=character_visit_ordinal,
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
