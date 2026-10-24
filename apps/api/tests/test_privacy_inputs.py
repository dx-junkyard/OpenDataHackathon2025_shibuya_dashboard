"""Personal details in posts are masked before the AI sees them; publishing warns (F-17, P-6)."""
from app.routes.issues import personal_info_warnings, redact_personal_info


def test_house_address_and_phone_are_masked_but_place_names_stay():
    text = redact_personal_info("近所の方（恵比寿3丁目12-5、0312345678）も神宮前1丁目10番1号の前で待っていました。恵比寿3丁目の公園は空いています")
    assert "12-5" not in text and "0312345678" not in text and "10番1号" not in text
    assert "恵比寿3丁目の公園" in text


def test_publishing_text_with_a_house_address_is_flagged():
    assert personal_info_warnings("場所: 恵比寿3丁目12-5") == ["番地までの住所"]
    assert personal_info_warnings("場所: 代々木上原駅周辺") == []
