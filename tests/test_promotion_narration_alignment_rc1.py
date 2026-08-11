from pathlib import Path

from az_enterprise.core.promotion_narration_alignment_rc1 import (
    PromotionNarrationAlignmentRC1,
)


def test_unicode_tokenization():

    tokens = (
        PromotionNarrationAlignmentRC1
        ._unicode_tokens(
            "\u0412 "
            "\u0410\u0440\u043a\u0442\u0438\u043a\u0435 "
            "\u0435\u0441\u0442\u044c "
            "\u043c\u0435\u0441\u0442\u0430, "
            "\u0433\u0434\u0435 "
            "\u0447\u0435\u043b\u043e\u0432\u0435\u043a "
            "\u0438\u0441\u0447\u0435\u0437\u0430\u0435\u0442."
        )
    )

    assert len(tokens) == 7
    assert tokens[0] == "\u0412"
    assert tokens[-1] == "\u0438\u0441\u0447\u0435\u0437\u0430\u0435\u0442"


def test_text_weight_is_unicode_safe():

    value = (
        PromotionNarrationAlignmentRC1
        ._text_weight(
            "\u041a\u043e\u0440\u0430\u0431\u043b\u0438 "
            "\u0438\u0441\u0447\u0435\u0437\u043b\u0438 "
            "\u0432\u043e "
            "\u043b\u044c\u0434\u0430\u0445 "
            "\u0410\u0440\u043a\u0442\u0438\u043a\u0438."
        )
    )

    assert value == 5


def test_block_scene_contract():

    mapping = (
        PromotionNarrationAlignmentRC1
        .BLOCK_SCENES
    )

    assert list(mapping[1]) == list(
        range(1, 8)
    )

    assert list(mapping[2]) == list(
        range(8, 13)
    )

    assert list(mapping[3]) == list(
        range(13, 18)
    )

    assert list(mapping[4]) == list(
        range(18, 24)
    )

    assert list(mapping[5]) == list(
        range(24, 30)
    )

    assert list(mapping[6]) == list(
        range(30, 36)
    )

    all_scenes = []

    for value in mapping.values():
        all_scenes.extend(
            list(value)
        )

    assert all_scenes == list(
        range(1, 36)
    )
