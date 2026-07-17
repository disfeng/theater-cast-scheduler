from dataclasses import dataclass, field


@dataclass(frozen=True)
class WishDraft:
    actor_name: str
    role_name: str
    player_name: str
    raw_note: str
    raw_line: str


@dataclass(frozen=True)
class DesignationSuggestion:
    actor_name: str
    role_name: str
    player_name: str | None
    suggested_type: str
    raw_line: str


@dataclass(frozen=True)
class PlayerDraft:
    label: str
    role_name: str
    relation: str | None
    player_name: str


@dataclass(frozen=True)
class ImportDraft:
    wishes: list[WishDraft] = field(default_factory=list)
    designation_suggestions: list[DesignationSuggestion] = field(default_factory=list)
    players: list[PlayerDraft] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    unresolved_lines: list[str] = field(default_factory=list)
