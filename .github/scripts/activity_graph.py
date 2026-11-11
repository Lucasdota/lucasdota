#!/usr/bin/env python3
"""Draw the last 31 days of GitHub contributions as an SVG line graph.

Runs inside the "Update README cards" workflow. Uses only the Python
standard library, so the workflow needs no extra installs.
"""
import json
import math
import os
import sys
import urllib.request
from datetime import date
from xml.sax.saxutils import escape

LOGIN = os.environ.get("GH_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.environ.get("OUT", "profile/activity-graph.svg")
DAYS = 31

# Colors match the other cards in the README
BG, BORDER, GRID = "#0d1117", "#30363d", "#21262d"
TEXT, MUTED, ACCENT = "#c9d1d9", "#8b949e", "#95BF47"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_days():
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "readme-activity-graph",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise RuntimeError(f"GitHub API error: {payload.get('errors')}")
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    return [(d["date"], d["contributionCount"]) for d in days][-DAYS:]


def nice_max(value):
    """Round the y-axis top up to a tidy number with 4 steps."""
    if value <= 4:
        return 4
    step = value / 4
    magnitude = 10 ** math.floor(math.log10(step))
    for mult in (1, 2, 2.5, 5, 10):
        if step <= mult * magnitude:
            return int(mult * magnitude * 4)
    return int(value)


def render(days, login):
    w, h = 1000, 340
    left, right, top, bottom = 64, 28, 74, 58
    pw, ph = w - left - right, h - top - bottom
    counts = [c for _, c in days]
    ymax = nice_max(max(counts) if counts else 0)
    n = len(days)

    def x(i):
        return left + (pw * i / (n - 1) if n > 1 else pw / 2)

    def y(c):
        return top + ph * (1 - c / ymax)

    pts = [(x(i), y(c)) for i, c in enumerate(counts)]
    line = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
    area = f"{line} L {pts[-1][0]:.1f} {top + ph} L {pts[0][0]:.1f} {top + ph} Z"
    total = sum(counts)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{escape(login)} contributions in the last {n} days">',
        "<style>",
        "text{font-family:'Segoe UI',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif}",
        ".line{stroke-dasharray:1;animation:draw 1.6s ease-out both}",
        ".area,.dot{animation:fade .8s ease-out 1.2s both}",
        "@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}",
        "@keyframes fade{from{opacity:0}to{opacity:1}}",
        "</style>",
        "<defs><linearGradient id=\"fill\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">"
        f'<stop offset="0%" stop-color="{ACCENT}" stop-opacity=".35"/>'
        f'<stop offset="100%" stop-color="{ACCENT}" stop-opacity="0"/>'
        "</linearGradient></defs>",
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="6" fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="{left - 34}" y="40" fill="{ACCENT}" font-size="20" font-weight="600">'
        f"{escape(login)}’s Contribution Graph</text>",
        f'<text x="{w - right}" y="40" fill="{MUTED}" font-size="13" text-anchor="end">'
        f"{total} contributions in the last {n} days</text>",
    ]

    for k in range(5):
        val = ymax * k / 4
        gy = y(val)
        parts.append(
            f'<line x1="{left}" y1="{gy:.1f}" x2="{left + pw}" y2="{gy:.1f}" '
            f'stroke="{GRID}" stroke-dasharray="{"0" if k == 0 else "4 4"}"/>'
        )
        label = f"{val:g}"
        parts.append(
            f'<text x="{left - 12}" y="{gy + 4:.1f}" fill="{MUTED}" font-size="12" '
            f'text-anchor="end">{label}</text>'
        )

    for i, (day, _) in enumerate(days):
        parts.append(
            f'<text x="{x(i):.1f}" y="{top + ph + 22}" fill="{MUTED}" font-size="11" '
            f'text-anchor="middle">{date.fromisoformat(day).day}</text>'
        )

    parts += [
        f'<text x="{left + pw / 2:.1f}" y="{h - 10}" fill="{TEXT}" font-size="12" '
        'text-anchor="middle">Days</text>',
        f'<text x="18" y="{top + ph / 2:.1f}" fill="{TEXT}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 18 {top + ph / 2:.1f})">Contributions</text>',
        f'<path class="area" d="{area}" fill="url(#fill)"/>',
        f'<path class="line" d="{line}" fill="none" stroke="{ACCENT}" stroke-width="2.5" '
        'stroke-linejoin="round" stroke-linecap="round" pathLength="1"/>',
    ]
    for (px, py), (day, c) in zip(pts, days):
        parts.append(
            f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="#ffffff" '
            f'stroke="{ACCENT}" stroke-width="1.5"><title>{day}: {c}</title></circle>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if not LOGIN or not TOKEN:
        sys.exit("GH_LOGIN and GH_TOKEN must be set")
    svg = render(fetch_days(), LOGIN)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(svg)
    os.replace(tmp, OUT)  # only replace yesterday's graph once the new one is complete
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
