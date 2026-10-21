#!/usr/bin/env python3
"""Generate docs/images/hero.svg: an animated HUD banner (pure SVG, SMIL animation, no scripts, no external files).

  scripts/make_hero.py            writes docs/images/hero.svg

The animation runs wherever SVG animation does: GitHub README images, browsers, most Markdown viewers.
"""
import math
import random
from pathlib import Path

W, H = 1280, 440
CX, CY = 268, 222
CYAN, ICE = "#22d3ee", "#a5f3fc"
FONT = "'Segoe UI','Helvetica Neue',system-ui,-apple-system,Roboto,Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"
rnd = random.Random(7)

out: list[str] = []
add = out.append


def spin(dur: float, cw: bool = True, cx: float = CX, cy: float = CY) -> str:
    a, b = (0, 360) if cw else (360, 0)
    return (f'<animateTransform attributeName="transform" type="rotate" from="{a} {cx} {cy}" to="{b} {cx} {cy}" '
            f'dur="{dur}s" repeatCount="indefinite"/>')


def polar(r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg - 90)
    return CX + r * math.cos(a), CY + r * math.sin(a)


add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
    f'aria-labelledby="t d">')
add('<title id="t">hermes-jarvis</title>')
add('<desc id="d">An animated sci-fi heads-up display: rotating rings around a pulsing core, a voice waveform, '
    'and the words hermes-jarvis, your AI agent, by voice.</desc>')

# ---------------------------------------------------------------- definitions
add(f'''<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#03070f"/><stop offset=".55" stop-color="#07111f"/><stop offset="1" stop-color="#0a1a2e"/></linearGradient>
  <radialGradient id="halo" cx="{CX}" cy="{CY}" r="330" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{CYAN}" stop-opacity=".30"/><stop offset=".5" stop-color="#0891b2" stop-opacity=".10"/><stop offset="1" stop-color="#0891b2" stop-opacity="0"/></radialGradient>
  <radialGradient id="core" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffffff"/><stop offset=".25" stop-color="{ICE}"/><stop offset=".6" stop-color="{CYAN}" stop-opacity=".85"/><stop offset="1" stop-color="#0891b2" stop-opacity="0"/></radialGradient>
  <linearGradient id="title" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="{ICE}"/><stop offset="1" stop-color="#38bdf8"/></linearGradient>
  <linearGradient id="band" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".5" stop-color="{CYAN}" stop-opacity=".16"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>
  <linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  <linearGradient id="bars" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#0e7490"/><stop offset="1" stop-color="{ICE}"/></linearGradient>
  <pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r=".9" fill="#38bdf8" opacity=".22"/></pattern>
  <pattern id="lines" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity=".28"/></pattern>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="glow2" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="card"><rect width="{W}" height="{H}" rx="20"/></clipPath>
  <clipPath id="tick"><rect x="540" y="408" width="688" height="22"/></clipPath>
</defs>''')

# ---------------------------------------------------------------- background
add('<g clip-path="url(#card)">')
add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
add(f'<rect width="{W}" height="{H}" fill="url(#dots)"/>')
add(f'<rect width="{W}" height="{H}" fill="url(#halo)"/>')
# a slow scan band sweeping down the whole card
add(f'<rect x="0" y="-90" width="{W}" height="90" fill="url(#band)"><animateTransform attributeName="transform" '
    f'type="translate" from="0 0" to="0 {H + 90}" dur="7s" repeatCount="indefinite"/></rect>')

# ---------------------------------------------------------------- the HUD
# faint reticle: cross hairs and a wide guide circle
add(f'<g stroke="{CYAN}" stroke-opacity=".22" stroke-width="1" fill="none">'
    f'<line x1="{CX - 232}" y1="{CY}" x2="{CX + 232}" y2="{CY}"/><line x1="{CX}" y1="{CY - 214}" x2="{CX}" y2="{CY + 214}"/>'
    f'<circle cx="{CX}" cy="{CY}" r="206" stroke-dasharray="2 10"/></g>')

# outer hairline + slowly turning tick ring
add(f'<circle cx="{CX}" cy="{CY}" r="190" fill="none" stroke="{CYAN}" stroke-opacity=".55" stroke-width="1.2"/>')
add(f'<g><circle cx="{CX}" cy="{CY}" r="183" fill="none" stroke="{ICE}" stroke-opacity=".6" stroke-width="9" '
    f'stroke-dasharray="1.4 8.2"/>{spin(90)}</g>')

# thick segmented ring, counter-clockwise
add(f'<g><circle cx="{CX}" cy="{CY}" r="164" fill="none" stroke="{CYAN}" stroke-opacity=".85" stroke-width="10" '
    f'stroke-dasharray="150 22 64 22 190 22 38 22 112 22 70 22" filter="url(#glow)"/>{spin(34, cw=False)}</g>')

# glowing arcs, clockwise and quick
add(f'<g><circle cx="{CX}" cy="{CY}" r="144" fill="none" stroke="{ICE}" stroke-width="3" stroke-linecap="round" '
    f'stroke-dasharray="88 140 26 140 12 200" filter="url(#glow2)"/>{spin(11)}</g>')

# fine tick ring, slow counter-clockwise
add(f'<g><circle cx="{CX}" cy="{CY}" r="124" fill="none" stroke="{CYAN}" stroke-opacity=".5" stroke-width="14" '
    f'stroke-dasharray="1 4.6"/>{spin(46, cw=False)}</g>')

# solid ring with three triangular markers
tri = []
for ang in (0, 120, 240):
    x, y = polar(108, ang)
    x2, y2 = polar(98, ang - 4.5)
    x3, y3 = polar(98, ang + 4.5)
    tri.append(f'<polygon points="{x:.1f},{y:.1f} {x2:.1f},{y2:.1f} {x3:.1f},{y3:.1f}" fill="{ICE}"/>')
add(f'<g><circle cx="{CX}" cy="{CY}" r="104" fill="none" stroke="{CYAN}" stroke-opacity=".65" stroke-width="1.4"/>'
    f'{"".join(tri)}{spin(17)}</g>')

# the Voice PE's twelve LEDs: a listening sweep chasing around the ring
leds = []
for i in range(12):
    x, y = polar(84, i * 30)
    begin = round(i * 0.16, 2)
    leds.append(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.2" fill="{ICE}" opacity=".25">'
        f'<animate attributeName="opacity" values=".18;1;.18;.18" keyTimes="0;.08;.42;1" dur="1.92s" begin="{begin}s" '
        f'repeatCount="indefinite"/>'
        f'<animate attributeName="r" values="4.4;6.6;4.4;4.4" keyTimes="0;.08;.42;1" dur="1.92s" begin="{begin}s" '
        f'repeatCount="indefinite"/></circle>')
add(f'<circle cx="{CX}" cy="{CY}" r="84" fill="none" stroke="{CYAN}" stroke-opacity=".28" stroke-width="1"/>')
add(f'<g filter="url(#glow)">{"".join(leds)}</g>')

# a voice ring: 40 short bars that dance, as if it were listening
bars = []
for i in range(40):
    ang = i * 9
    h0 = rnd.uniform(5, 12)
    vals = ";".join(f"{CY - 56 - rnd.uniform(4, 20):.1f}" for _ in range(5))
    vals += f";{CY - 56 - h0:.1f}"
    dur = round(rnd.uniform(0.7, 1.5), 2)
    bars.append(f'<line x1="{CX}" y1="{CY - 56}" x2="{CX}" y2="{CY - 56 - h0:.1f}" transform="rotate({ang} {CX} {CY})">'
                f'<animate attributeName="y2" values="{vals}" dur="{dur}s" repeatCount="indefinite"/></line>')
add(f'<g stroke="{ICE}" stroke-width="2.2" stroke-linecap="round" opacity=".9">{"".join(bars)}</g>')

# inner dotted ring and the pulsing core
add(f'<g><circle cx="{CX}" cy="{CY}" r="48" fill="none" stroke="{ICE}" stroke-opacity=".5" stroke-width="1" '
    f'stroke-dasharray="3 7"/>{spin(13, cw=False)}</g>')
add(f'<circle cx="{CX}" cy="{CY}" r="42" fill="url(#core)" filter="url(#glow2)">'
    f'<animate attributeName="r" values="38;46;38" dur="2.6s" repeatCount="indefinite"/>'
    f'<animate attributeName="opacity" values=".85;1;.85" dur="2.6s" repeatCount="indefinite"/></circle>')
add(f'<circle cx="{CX}" cy="{CY}" r="15" fill="#fff" opacity=".95"><animate attributeName="r" values="13;18;13" '
    f'dur="2.6s" repeatCount="indefinite"/></circle>')

# satellites on three orbits
for r, dur, cw, size, col in ((178, 9, True, 4.5, "#ffffff"), (150, 14, False, 3.5, ICE), (131, 6.5, True, 3, CYAN)):
    x, y = polar(r, 0)
    add(f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="{size}" fill="{col}" filter="url(#glow2)"/>{spin(dur, cw)}</g>')

# the pipeline, clockwise from the top left: the labels sit on the diagonals so nothing touches the card edge
for txt, ang, anchor in (("WAKE", 315, "end"), ("STT", 45, "start"), ("AGENT", 135, "start"), ("VOICE", 225, "end")):
    x, y = polar(214, ang)
    dx = 6 if anchor == "start" else -6
    add(f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" font-family="{MONO}" font-size="11" letter-spacing="3" '
        f'fill="{CYAN}" fill-opacity=".8" text-anchor="{anchor}">{txt}</text>')

# ---------------------------------------------------------------- the text block
X0 = 540
add(f'<g font-family="{MONO}" font-size="12.5" letter-spacing="3" fill="{CYAN}">'
    f'<circle cx="{X0 + 4}" cy="74" r="4" fill="#34d399" filter="url(#glow)"><animate attributeName="opacity" '
    f'values="1;.25;1" dur="1.6s" repeatCount="indefinite"/></circle>'
    f'<text x="{X0 + 18}" y="78.5" fill-opacity=".85">SYSTEM ONLINE</text>'
    f'<text x="{W - 52}" y="78.5" text-anchor="end" fill-opacity=".6">LISTENING<tspan>'
    f'<animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite"/>_</tspan></text></g>')

add(f'<text x="{X0}" y="168" font-family="{FONT}" font-size="76" font-weight="700" letter-spacing="5" '
    f'fill="url(#title)" filter="url(#glow)">HERMES<tspan fill="{CYAN}" font-weight="300">-</tspan>JARVIS</text>')

# a highlight that travels along the rule under the title
add(f'<line x1="{X0}" y1="190" x2="{W - 52}" y2="190" stroke="{CYAN}" stroke-opacity=".35" stroke-width="1.5"/>')
add(f'<rect x="{X0}" y="188.2" width="140" height="3.6" rx="1.8" fill="url(#sweep)" filter="url(#glow)">'
    f'<animate attributeName="x" values="{X0};{W - 52 - 140};{X0}" dur="5.5s" repeatCount="indefinite"/></rect>')

add(f'<text x="{X0}" y="236" font-family="{FONT}" font-size="27" font-weight="300" letter-spacing=".6" '
    f'fill="#c9e3f7">Your AI agent, by voice. <tspan fill="{ICE}" font-weight="600">Fast, interruptible, yours.</tspan></text>')

# status chips (monospace text is about 9.4 px per character at this size and spacing)
CH = 9.4
chips = (("WAKE", "ON DEVICE", 0), ("BRAIN", "HERMES / ANY LLM", 0.5), ("VOICE", "PIPER, LOCAL", 1.0))
x = X0
for label, val, delay in chips:
    w = 30 + len(label) * CH + 14 + len(val) * CH + 12
    add(f'<g font-family="{MONO}" font-size="12.5" letter-spacing="1.6">'
        f'<rect x="{x:.0f}" y="262" width="{w:.0f}" height="32" rx="6" fill="{CYAN}" fill-opacity=".07" stroke="{CYAN}" '
        f'stroke-opacity=".55"/>'
        f'<circle cx="{x + 15:.0f}" cy="278" r="3.6" fill="#34d399"><animate attributeName="opacity" values="1;.2;1" '
        f'dur="2.2s" begin="{delay}s" repeatCount="indefinite"/></circle>'
        f'<text x="{x + 30:.0f}" y="282.5" fill="{ICE}" fill-opacity=".75">{label}</text>'
        f'<text x="{x + 30 + len(label) * CH + 14:.0f}" y="282.5" fill="#fff">{val}</text></g>')
    x += w + 10

# equalizer along the bottom right
eq = []
n, x_start, x_end, base = 46, X0, W - 52, 392
step = (x_end - x_start) / n
for i in range(n):
    bx = x_start + i * step
    centre = 1 - abs(i - n / 2) / (n / 2)            # taller in the middle
    top = 14 + 46 * centre
    heights = [round(rnd.uniform(5, top), 1) for _ in range(6)]
    heights.append(heights[0])
    dur = round(rnd.uniform(0.8, 1.9), 2)
    hv = ";".join(str(h) for h in heights)
    yv = ";".join(f"{base - h:.1f}" for h in heights)
    eq.append(f'<rect x="{bx:.1f}" y="{base - heights[0]:.1f}" width="{step * 0.56:.1f}" height="{heights[0]}" rx="1.5" '
              f'fill="url(#bars)"><animate attributeName="height" values="{hv}" dur="{dur}s" repeatCount="indefinite"/>'
              f'<animate attributeName="y" values="{yv}" dur="{dur}s" repeatCount="indefinite"/></rect>')
add(f'<line x1="{X0}" y1="{base + 4}" x2="{W - 52}" y2="{base + 4}" stroke="{CYAN}" stroke-opacity=".3"/>')
add(f'<g filter="url(#glow)" opacity=".95">{"".join(eq)}</g>')

# a ticker at the very bottom
ticker = ("HEY JARVIS  ▸  WHAT'S ON MY CALENDAR TODAY  ▸  ONE MOMENT, SIR  ▸  CHECKING YOUR CALENDAR  ▸  "
          "YOU HAVE THREE MEETINGS  ▸  STOP  ▸  ")
add(f'<g clip-path="url(#tick)"><text y="424" font-family="{MONO}" font-size="11" letter-spacing="2.4" fill="{CYAN}" '
    f'fill-opacity=".55">{ticker * 2}<animateTransform attributeName="transform" type="translate" from="{X0} 0" '
    f'to="{X0 - 560} 0" dur="22s" repeatCount="indefinite"/></text></g>')

# ---------------------------------------------------------------- frame: scanlines, corner brackets, border
add(f'<rect width="{W}" height="{H}" fill="url(#lines)" opacity=".5"/>')
m, L = 16, 34
corners = (f"M{m},{m + L} V{m} H{m + L}", f"M{W - m - L},{m} H{W - m} V{m + L}",
           f"M{m},{H - m - L} V{H - m} H{m + L}", f"M{W - m - L},{H - m} H{W - m} V{H - m - L}")
add(f'<g fill="none" stroke="{ICE}" stroke-width="2.2" stroke-linecap="square" filter="url(#glow)">'
    + "".join(f'<path d="{c}"/>' for c in corners) + '</g>')
add('</g>')
add(f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="20" fill="none" stroke="{CYAN}" stroke-opacity=".35" '
    f'stroke-width="1.5"/>')
add('</svg>')

dest = Path(__file__).resolve().parent.parent / "docs" / "images" / "hero.svg"
dest.write_text("\n".join(out) + "\n")
print(f"wrote {dest} ({dest.stat().st_size // 1024} KiB)")
