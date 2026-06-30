from html import escape


def kbd_table(rows, active_value=None, null_active=False):
    KBD = (
        "background-color: #f0f0f0;"
        "border: 1px solid #aaaaaa;"
        "padding: 2px 7px;"
        "font-family: monospace;"
        "font-weight: bold;"
    )
    parts = []
    for key, value in rows:
        is_active = (value is None and null_active) or (
            value is not None
            and active_value is not None
            and str(value) == active_value
        )
        dot_color = "black" if is_active else "transparent"
        display_value = "&#8709;&thinsp;NULL" if value is None else escape(str(value))
        parts.append(
            f"<tr>"
            f'<td style="text-align: center; vertical-align: middle; font-size: 7px;'
            f' color: {dot_color};">&#9679;</td>'
            f'<td align="center" style="{KBD}">{escape(str(key))}</td>'
            f'<td style="padding: 2px 6px; font-family: monospace;">{display_value}</td>'
            f"</tr>"
        )
    return f'<table cellspacing="3" cellpadding="0">{"".join(parts)}</table>'
