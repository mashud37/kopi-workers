"""Draw the kopi mascot, a leaning blue pencil with big eyes, as pixel-art SVG, and hold its tips.
Every page shows kopi in its corner, where it gives these tips.
"""
import hashlib

from markupsafe import Markup

KOPI = [
    "............ooooooooo.......",
    "...........opppppppppo......",
    "...........ooooooooooo......",
    "...........oGGGGGGGhho......",
    "..........ooooooooooo.......",
    "..........olbbbbbbbbo.......",
    "..........oloobbboobo.o.....",
    "..........olbbbbbbbbo.o.....",
    ".........olwwwbwwwbo..o.....",
    ".........olwEEbwEEbo..o.....",
    ".........olweebweebo.o......",
    ".........olwwwbwwwboo.......",
    "........olbbbbbbbboo........",
    "........olbbboobbbo.........",
    ".......oolbbbbbbbbo.........",
    "......o.olbbbbbbbbo.........",
    "......oolbbbbbbbbo..........",
    "......oolbbbbbbbbo..........",
    ".......otttttTTTTo..........",
    "........ottttTTTo...........",
    "........otttTTo.............",
    ".........ottTo.o............",
    ".........ooqqo.o............",
    ".........o.oo..o............",
    ".........o.....o............",
    ".........o.....o............",
    ".........o.....o............",
    "........oo.....oo...........",
]

COLOURS = {
    "o": "#1f1f1f",
    "p": "#f6aea9",
    "G": "#dadce0",
    "h": "#9aa0a6",
    "b": "#8ab4f8",
    "l": "#d2e3fc",
    "w": "#ffffff",
    "e": "#1f1f1f",
    "E": "#1f1f1f",
    "t": "#f6d7a7",
    "T": "#e3b97a",
    "q": "#1a73e8",
}

# Changes whenever the drawing does, so a browser fetches the new tab icon instead of its cached one.
VERSION = hashlib.sha1("".join(KOPI).encode()).hexdigest()[:8]

# The lead ("q") is "ink", which blinks while a job runs, as if the pencil were writing.
PARTS = {
    "q": "ink",
    "e": "eye",
    "E": "eye",
}

# What kopi says when clicked, by the first part of the page's address.
TIPS = {
    "": [
        "Pick an app. Each one works on its own.",
        "Drop a file on an app's page and it lands in that app's input folder.",
    ],
    "apps": [
        "Drop files anywhere on this page to add them.",
        "The newest file you added is already chosen in each form.",
        "Settings decide which model runs. Blank means the app's own file.",
        "Analyse and proof cost nothing. Edit may call a paid model.",
    ],
    "jobs": [
        "Every run keeps its log here, finished or not.",
    ],
    "keys": [
        "Keys are kept on this computer, outside your project folder.",
        "Give a key to every app at once, or choose per app.",
    ],
}
GREETING = "Hello! Click me for a tip."


def pixel(column, row, colour):
    """One square of the drawing; its column lets the stylesheet stagger an animation."""
    return f'<rect x="{column}" y="{row}" width="1" height="1" fill="{colour}" style="--i:{column}"/>'


def svg(scale):
    """The mascot as inline SVG, with each part grouped so the stylesheet can animate it.

    An upper eye pixel ("E") also gets a white lid on top, which the blink animation shows.

    Args:
        scale: screen pixels per drawing pixel.
    """
    groups = {"twin": [], "body": [], "ink": [], "eye": [], "lid": []}
    for row, line in enumerate(KOPI):
        for column, character in enumerate(line):
            if character == ".":
                continue
            part = PARTS.get(character, "body")
            groups[part].append(pixel(column, row, COLOURS[character]))
            if part == "eye":
                groups["body"].append(pixel(column, row, COLOURS["w"]))
            if character == "E":
                groups["lid"].append(pixel(column, row, COLOURS["w"]))

    drawing = []
    for part, rects in groups.items():
        drawing.append(f'<g class="{part}">{"".join(rects)}</g>')
    cells = len(KOPI)
    size = cells * scale
    opening = f'<svg class="mascot mascot-kopi" viewBox="0 0 {cells} {cells}" width="{size}" height="{size}" shape-rendering="crispEdges" role="img" aria-label="kopi">'
    return Markup(opening + '<g class="figure">' + "".join(drawing) + "</g></svg>")
