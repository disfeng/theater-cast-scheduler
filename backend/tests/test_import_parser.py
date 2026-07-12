from app.services.import_parser import parse_group_board


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
