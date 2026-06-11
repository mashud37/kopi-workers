"""Segoe Fluent Icons helper.

Segoe Fluent Icons ships with Windows 11 (C:\\Windows\\Fonts\\SegoeIcons.ttf) and is
the icon set PowerPoint's own icon picker draws from. Glyphs live in the Private
Use Area, so they render only where the font is installed — true for PowerPoint
(our primary PDF path). The LibreOffice fallback may show blanks for these.

Code points below were verified visually against the installed font.
"""

from pptx.util import Pt

ICON_FONT = "Segoe Fluent Icons"

# semantic name -> verified PUA code point
ICONS = {
    "people": "",
    "person": "",
    "settings": "",
    "method": "",       
    "process": "",
    "globe": "",
    "world": "",
    "check": "",
    "warning": "",
    "info": "",
    "doc": "",
    "document": "",
    "data": "",         
    "clipboard": "",
    "search": "",
    "link": "",
    "star": "",
    "chart": "",        
    "piechart": "",
    "trend": "",        
    "growth": "",
    "idea": "",         
    "lightbulb": "",
    "shop": "",
    "cart": "",
    "share": "",
    "phone": "",
    "clock": "",
    "time": "",
    "lock": "",
    "card": "",
    "money": "",
    "payment": "",
    "comment": "",
    "discourse": "",
    "chat": "",
    "books": "",
    "library": "",
    "sparkle": "",
    "list": "",
    "flag": "",
    "goal": "",
    "target": "",
    "shield": "",
    "security": "",
    "view": "",
    "attention": "",
    "tag": "",
    "question": "",
    "computer": "",
    "device": "",
}

# section-name keyword -> default icon name
SECTION_ICONS = {
    "context": "globe",
    "background": "globe",
    "intro": "globe",
    "method": "method",
    "data": "clipboard",
    "approach": "settings",
    "find": "chart",
    "result": "chart",
    "discuss": "idea",
    "implic": "idea",
    "conclu": "check",
}


def glyph(name):
    """Return the glyph char for a semantic name, or None if unknown."""
    if not name:
        return None
    return ICONS.get(str(name).strip().lower())


def section_glyph(section):
    s = str(section or "").lower()
    for key, name in SECTION_ICONS.items():
        if key in s:
            return ICONS[name]
    return None


EMOJI_FONT = "Segoe UI Emoji"

# semantic name -> emoji (used only in --emoji mode)
EMOJI = {
    "people": "👥", "person": "🧑", "settings": "⚙️", "method": "🔬",
    "process": "🔄", "globe": "🌐", "world": "🌍", "check": "✅",
    "warning": "⚠️", "info": "ℹ️", "doc": "📄", "document": "📄",
    "data": "📋", "clipboard": "📋", "search": "🔍", "link": "🔗",
    "star": "⭐", "chart": "📊", "piechart": "📊", "trend": "📈",
    "growth": "📈", "idea": "💡", "lightbulb": "💡", "shop": "🛍️",
    "cart": "🛒", "share": "📤", "phone": "📱", "clock": "⏰",
    "time": "⏳", "lock": "🔒", "card": "💳", "money": "💰",
    "payment": "💳", "comment": "💬", "discourse": "💬", "chat": "💬",
    "books": "📚", "library": "📚", "sparkle": "✨", "list": "📝",
    "flag": "🚩", "goal": "🎯", "target": "🎯", "shield": "🛡️",
    "security": "🔐", "view": "👀", "attention": "👀", "tag": "🏷️",
    "question": "❓", "computer": "💻", "device": "📱", "robot": "🤖",
}


def _looks_like_emoji(s):
    return bool(s) and any(ord(c) > 0x2000 for c in str(s))


def resolve_icon(name, use_emoji=False):
    """Return (char, font) for a semantic name, or (None, None) if unresolvable.

    Default = Fluent vector glyph. With use_emoji=True, return the emoji form.
    If the value passed is itself an emoji char, it is passed through.
    """
    if not name:
        return None, None
    key = str(name).strip().lower()
    if use_emoji:
        ch = EMOJI.get(key) or (name if _looks_like_emoji(name) else None)
        return (ch, EMOJI_FONT) if ch else (None, None)
    ch = ICONS.get(key)
    if ch:
        return ch, ICON_FONT
    if _looks_like_emoji(name):  # LLM handed us an emoji; render it as emoji
        return name, EMOJI_FONT
    return None, None


def add_icon_run(paragraph, name, size_pt, color):
    """Append an icon glyph run to a paragraph. Returns the run, or None if the
    name is unknown (caller can skip without breaking)."""
    ch = glyph(name)
    if ch is None:
        return None
    r = paragraph.add_run()
    r.text = ch
    r.font.name = ICON_FONT
    r.font.size = Pt(size_pt)
    if color is not None:
        r.font.color.rgb = color
    return r
