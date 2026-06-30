from core.rendering import kbd_table


def test_keys_and_values_appear():
    html = kbd_table([("1", "accept"), ("2", "reject")])
    assert "1" in html
    assert "accept" in html
    assert "2" in html
    assert "reject" in html


def test_active_value_bullet_is_black():
    html = kbd_table([("1", "accept"), ("2", "reject")], active_value="accept")
    assert "color: black" in html


def test_inactive_value_bullet_is_transparent():
    html = kbd_table([("1", "accept"), ("2", "reject")], active_value="accept")
    assert "color: transparent" in html


def test_no_active_value_all_transparent():
    html = kbd_table([("1", "accept"), ("2", "reject")], active_value=None)
    assert "color: black" not in html


def test_html_characters_are_escaped():
    html = kbd_table([("<b>", "<script>alert(1)</script>")])
    assert "<b>" not in html
    assert "<script>" not in html
    assert "&lt;b&gt;" in html


def test_null_value_displays_null_symbol():
    html = kbd_table([("1", None)])
    assert "NULL" in html


def test_null_value_active_when_null_active():
    html = kbd_table([("1", None)], null_active=True)
    assert "color: black" in html


def test_null_value_inactive_when_not_null_active():
    html = kbd_table([("1", None)], null_active=False)
    assert "color: black" not in html


def test_null_active_does_not_highlight_non_null_shortcuts():
    html = kbd_table([("1", "accept"), ("2", None)], null_active=True)
    assert html.count("color: black") == 1
