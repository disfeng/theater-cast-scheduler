from app.schemas.performance_boards import ParsedPerformancePlayer
from app.services.import_parser import parse_group_board, parse_player_registration


def test_parse_group_board_extracts_wishes_players_and_notes():
    text = """
#指定信息⬇️
【虔诚许愿】-小展/长离-Jennifer 山风昭昭可以原地转十个圈
热力榜三-文轩/轩辕重光（四月热力榜-兹）
#玩家信息⬇️
女位：
【昭昭】长离（恋）： Jennifer-14-3
【观禾】轩辕重光（恋）：嘻嘻
#场内点心⬇️
昭昭：
放房间：两瓶水，蓝莓
#其他备注⬇️
观禾：开观禾2.0
"""

    draft = parse_group_board(text)

    assert draft.wishes[0].actor_name == "小展"
    assert draft.wishes[0].role_name == "长离"
    assert draft.wishes[0].player_name == "Jennifer"
    assert draft.designation_suggestions[0].suggested_type == "top_three"
    assert draft.players[0].label == "昭昭"
    assert draft.players[0].role_name == "长离"
    assert draft.notes["昭昭"] == "放房间：两瓶水，蓝莓"
    assert draft.notes["观禾"] == "开观禾2.0"


def test_parse_player_registration_extracts_trailing_visit_ordinals():
    assert parse_player_registration(
        "【昭昭】长离（恋）：Jennifer-14-3"
    ) == ParsedPerformancePlayer(
        player_name="Jennifer",
        player_character_name="昭昭",
        paired_role_name="长离",
        relation_label="恋",
        theater_visit_ordinal=14,
        character_visit_ordinal=3,
    )


def test_parse_player_registration_accepts_names_without_visit_suffix():
    parsed = parse_player_registration("【观禾】轩辕重光（恋）：Sally")
    assert parsed == ParsedPerformancePlayer("Sally", "观禾", "轩辕重光", "恋", None, None)


def test_parse_player_registration_only_treats_two_final_integers_as_suffix():
    assert parse_player_registration("【初晴】长离：初晴29-12").player_name == "初晴29-12"
    assert parse_player_registration("【初晴】长离：初晴-29-12").player_name == "初晴"
    assert parse_player_registration("【初晴】长离：sunny-2-x").player_name == "sunny-2-x"
    assert parse_player_registration("【初晴】长离：Sunny-x-2").player_name == "Sunny-x-2"
    assert (
        parse_player_registration("【初晴】长离：sunny-2-3-extra").player_name == "sunny-2-3-extra"
    )


def test_parse_player_registration_rejects_non_player_lines():
    assert parse_player_registration("女位：") is None
    assert parse_player_registration("昭昭：两瓶水") is None


def test_parse_wish_accepts_spaced_marker_and_player_inside_parentheses():
    draft = parse_group_board("""
#指定信息⬇️
【虔诚许愿】 -小A/林月棠（微醺未醒，开不到我将cos晴天娃娃）
""")

    assert len(draft.wishes) == 1
    assert draft.wishes[0].actor_name == "小A"
    assert draft.wishes[0].role_name == "林月棠"
    assert draft.wishes[0].player_name == "微醺未醒"
    assert draft.wishes[0].raw_note == "开不到我将cos晴天娃娃"


def test_real_board_keeps_actor_role_wish_extraction_with_suffix_players():
    draft = parse_group_board("""
#指定信息⬇️
【虔诚许愿】-小展/长离-Jennifer 山风昭昭可以原地转十个圈
热力榜三-文轩/轩辕重光（四月热力榜-兹）
#玩家信息⬇️
【昭昭】长离（恋）：Sunny-14-3
""")
    assert (draft.wishes[0].actor_name, draft.wishes[0].role_name, draft.wishes[0].player_name) == (
        "小展",
        "长离",
        "Jennifer",
    )
    assert (
        draft.designation_suggestions[0].actor_name,
        draft.designation_suggestions[0].role_name,
    ) == ("文轩", "轩辕重光")
