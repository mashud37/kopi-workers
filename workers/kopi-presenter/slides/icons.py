"""Map slide icon names to Segoe Fluent Icons code points, the set PowerPoint's own
picker draws from. The glyphs render only where that font is installed.
"""

from pptx.util import Pt

ICON_FONT = "Segoe Fluent Icons"
EMOJI_FONT = "Segoe UI Emoji"

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

# semantic name -> emoji (used only in --emoji mode)
EMOJI = {
    "people": "👥",
    "person": "🧑",
    "settings": "⚙️",
    "method": "🔬",
    "process": "🔄",
    "globe": "🌐",
    "world": "🌍",
    "check": "✅",
    "warning": "⚠️",
    "info": "ℹ️",
    "doc": "📄",
    "document": "📄",
    "data": "📋",
    "clipboard": "📋",
    "search": "🔍",
    "link": "🔗",
    "star": "⭐",
    "chart": "📊",
    "piechart": "📊",
    "trend": "📈",
    "growth": "📈",
    "idea": "💡",
    "lightbulb": "💡",
    "shop": "🛍️",
    "cart": "🛒",
    "share": "📤",
    "phone": "📱",
    "clock": "⏰",
    "time": "⏳",
    "lock": "🔒",
    "card": "💳",
    "money": "💰",
    "payment": "💳",
    "comment": "💬",
    "discourse": "💬",
    "chat": "💬",
    "books": "📚",
    "library": "📚",
    "sparkle": "✨",
    "list": "📝",
    "flag": "🚩",
    "goal": "🎯",
    "target": "🎯",
    "shield": "🛡️",
    "security": "🔐",
    "view": "👀",
    "attention": "👀",
    "tag": "🏷️",
    "question": "❓",
    "computer": "💻",
    "device": "📱",
    "robot": "🤖",
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


def _looks_like_emoji(s):
    return bool(s) and any(ord(c) > 0x2000 for c in str(s))


def resolve_icon(name, use_emoji=False) -> dict:
    """The `char` and `font` for a semantic name, both None if it cannot be resolved.

    Default = Fluent vector glyph. With use_emoji=True, return the emoji form.
    If the value passed is itself an emoji char, it is passed through.
    """
    missing = {"char": None, "font": None}
    if not name:
        return missing
    key = str(name).strip().lower()
    if use_emoji:
        ch = EMOJI.get(key) or (name if _looks_like_emoji(name) else None)
        return {"char": ch, "font": EMOJI_FONT} if ch else missing
    ch = ICONS.get(key)
    if ch:
        return {"char": ch, "font": ICON_FONT}
    if _looks_like_emoji(name):  # LLM handed us an emoji; render it as emoji
        return {"char": name, "font": EMOJI_FONT}
    return missing


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
