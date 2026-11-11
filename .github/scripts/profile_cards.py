#!/usr/bin/env python3
"""Profile README cards: commits (with PRs and stars), languages and a wave footer.

Runs in the "Update README cards" workflow and writes three SVGs to profile/.
Standard library only. Set DEMO=1 to render with sample data instead of the API.
"""
import json
import math
import os
import random
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

LOGIN = os.environ.get("GH_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT_DIR = os.environ.get("OUT_DIR", "profile")
DEMO = os.environ.get("DEMO") == "1"

# Tools shown as chips under the languages card. Edit freely.
DAY_TO_DAY = ["Shopify", "React", "Next.js", "Tailwind CSS"]

# Shopify brand + Polaris palette
LIME, FOREST, TEAL, MINT, DEEP, GOLD = "#95BF47", "#5E8E3E", "#008060", "#AEE9D1", "#004C3F", "#FFC453"
CARD, BORDER, GRID = "#161b22", "#30363d", "#21262d"
TEXT, MUTED, FAINT = "#e6edf3", "#8b949e", "#6e7681"
LANG_COLORS = [LIME, TEAL, MINT, FOREST, GOLD]
OTHER_COLOR = "#4b5563"
FONT = "'Segoe UI',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ------------------------------------------------------------------ data
def month_windows(now):
    """The last 12 calendar months, ending with the current one."""
    y, m = now.year, now.month
    out = []
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    out.reverse()
    wins = []
    for (y, m) in out:
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        nxt = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc)
        end = min(nxt - timedelta(seconds=1), now)
        wins.append((y, m, start, end))
    return wins


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def graphql(query):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "readme-profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    if payload.get("errors") or not (payload.get("data") or {}).get("user"):
        raise RuntimeError(f"GitHub API error: {payload.get('errors')}")
    return payload["data"]["user"]


def fetch(now):
    wins = month_windows(now)
    parts = []
    for i, (_, _, start, end) in enumerate(wins):
        parts.append(f'''
    m{i}: contributionsCollection(from: "{iso(start)}", to: "{iso(end)}") {{
      restrictedContributionsCount
      totalPullRequestContributions
      commitContributionsByRepository(maxRepositories: 100) {{
        repository {{ nameWithOwner isPrivate }}
        contributions(first: 100) {{ nodes {{ commitCount }} }}
      }}
    }}''')
    parts.append(f'''
    year: contributionsCollection(from: "{iso(wins[0][2])}", to: "{iso(now)}") {{
      commitContributionsByRepository(maxRepositories: 100) {{
        repository {{
          nameWithOwner
          languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
            totalSize
            edges {{ size node {{ name }} }}
          }}
        }}
      }}
    }}''')
    user = graphql("query($login: String!) { user(login: $login) {" + "".join(parts) + "\n} }")

    stars_q = """query($login: String!) { user(login: $login) {
      repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                   orderBy: {field: STARGAZERS, direction: DESC}) {
        nodes {
          stargazerCount
          stargazers(first: 100, orderBy: {field: STARRED_AT, direction: DESC}) {
            edges { starredAt }
          }
        }
      }
    } }"""
    repos = graphql(stars_q)["repositories"]["nodes"]

    months = []
    repo_commits = defaultdict(int)
    for i, (y, m, start, end) in enumerate(wins):
        col = user[f"m{i}"]
        private = public = 0
        for entry in col["commitContributionsByRepository"]:
            n = sum(node["commitCount"] for node in entry["contributions"]["nodes"])
            repo_commits[entry["repository"]["nameWithOwner"]] += n
            if entry["repository"]["isPrivate"]:
                private += n
            else:
                public += n
        # private work GitHub counts but won't itemize (e.g. org repos the token can't open)
        private += col["restrictedContributionsCount"]
        months.append({"y": y, "m": m, "private": private, "public": public,
                       "prs": col["totalPullRequestContributions"], "stars": 0})

    for repo in repos:
        for edge in repo["stargazers"]["edges"]:
            t = datetime.strptime(edge["starredAt"], "%Y-%m-%dT%H:%M:%SZ")
            for mo in months:
                if (t.year, t.month) == (mo["y"], mo["m"]):
                    mo["stars"] += 1

    weights = defaultdict(float)
    for entry in user["year"]["commitContributionsByRepository"]:
        repo = entry["repository"]
        langs = repo["languages"]
        commits = repo_commits.get(repo["nameWithOwner"], 0)
        if not langs["totalSize"] or not commits:
            continue
        for edge in langs["edges"]:
            weights[edge["node"]["name"]] += commits * edge["size"] / langs["totalSize"]

    return {
        "months": months,
        "repos": sum(1 for v in repo_commits.values() if v > 0),
        "total_stars": sum(r["stargazerCount"] for r in repos),
        "languages": dict(weights),
    }


def demo_data(now):
    rng = random.Random(11)
    shape = [12, 19, 3, 18, 147, 102, 69, 77, 115, 32, 56, 41]
    months = []
    for i, (y, m, _, _) in enumerate(month_windows(now)):
        total = shape[i]
        public = total if i < 2 else (rng.choice([0, 0, 1, 2, 4]) if total else 0)
        months.append({"y": y, "m": m, "private": total - public, "public": public,
                       "prs": rng.choice([0, 1, 2, 3, 5, 8]) if total > 10 else 0,
                       "stars": rng.choice([0, 0, 0, 1, 2])})
    return {"months": months, "repos": 25, "total_stars": 18,
            "languages": {"Liquid": 531, "CSS": 228, "JavaScript": 161, "Astro": 43,
                          "TypeScript": 27, "SCSS": 6, "HTML": 4}}


# ------------------------------------------------------------------ svg helpers
def text_w(s, size, bold=False):
    """Rough text width for layout (no font metrics available server-side)."""
    per = 0.6 if bold else 0.55
    narrow = sum(1 for ch in s if ch in "il.,:;|!'1 ")
    return size * (per * (len(s) - narrow) + 0.3 * narrow)


def star_points(cx, cy, r):
    pts = []
    for k in range(10):
        rad = r if k % 2 == 0 else r * 0.45
        a = -math.pi / 2 + k * math.pi / 5
        pts.append(f"{cx + rad * math.cos(a):.1f},{cy + rad * math.sin(a):.1f}")
    return " ".join(pts)


def pr_icon(x, y, color):
    """Small pull-request style glyph: two branches merging."""
    return (f'<g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">'
            f'<circle cx="{x - 4}" cy="{y - 5}" r="2.2"/><circle cx="{x - 4}" cy="{y + 5}" r="2.2"/>'
            f'<line x1="{x - 4}" y1="{y - 2.8}" x2="{x - 4}" y2="{y + 2.8}"/>'
            f'<circle cx="{x + 5}" cy="{y + 5}" r="2.2"/>'
            f'<path d="M{x + 5} {y + 2.8} V{y - 2} Q{x + 5} {y - 5} {x + 2} {y - 5} H{x - 0.5}"/></g>')


def bar_path(x, y, w, h, r):
    """Bar with rounded top corners only."""
    r = min(r, h, w / 2)
    if h <= 0:
        return ""
    return (f"M{x:.1f} {y + h:.1f} V{y + r:.1f} Q{x:.1f} {y:.1f} {x + r:.1f} {y:.1f} "
            f"H{x + w - r:.1f} Q{x + w:.1f} {y:.1f} {x + w:.1f} {y + r:.1f} V{y + h:.1f} Z")


STYLE = f"""<style>
text{{font-family:{FONT}}}
.grow{{transform-box:fill-box;transform-origin:50% 100%;animation:grow .9s cubic-bezier(.2,.8,.2,1) both}}
.growx{{transform-box:fill-box;transform-origin:0 50%;animation:growx 1.1s cubic-bezier(.2,.8,.2,1) both}}
.fade{{animation:fade .6s ease-out both}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.6,.5,1) both}}
.twinkle{{animation:tw 2.6s ease-in-out infinite}}
@keyframes grow{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
@keyframes growx{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes pop{{from{{transform:scale(0)}}to{{transform:scale(1)}}}}
@keyframes tw{{0%,100%{{opacity:1}}50%{{opacity:.5}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>"""


def window_label(months):
    a, b = months[0], months[-1]
    return f"{MONTHS[a['m'] - 1]} {a['y']} – {MONTHS[b['m'] - 1]} {b['y']}"


# ------------------------------------------------------------------ commits card
def render_commits(d):
    months = d["months"]
    totals = [mo["private"] + mo["public"] for mo in months]
    total, priv, pub = sum(totals), sum(mo["private"] for mo in months), sum(mo["public"] for mo in months)
    prs = sum(mo["prs"] for mo in months)
    new_stars = sum(mo["stars"] for mo in months)
    has_star_row = new_stars > 0

    W = 860
    H = 446 if has_star_row else 414
    x0, x1 = 32, 790
    base, top = 300, 140
    slot = (x1 - x0) / 12
    bw = 34
    peak = max(totals) or 1
    scale = (base - top) / peak
    avg = total / 12

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'role="img" aria-label="{total} commits, {prs} pull requests and {new_stars} new stars '
         f'in the last 12 months">', STYLE,
         f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{CARD}" stroke="{BORDER}"/>']

    # header
    o.append(f'<text x="32" y="64" font-size="40" font-weight="800" fill="{LIME}">{total:,}'
             f'<tspan fill="{TEXT}" font-weight="700"> commits</tspan></text>')
    o.append(f'<text x="32" y="92" font-size="14" fill="{MUTED}">across {d["repos"]} repositories · '
             f'{window_label(months)}</text>')

    # legend (right-aligned): private / public
    items = [(LIME, "private", priv), (MINT, "public", pub)]
    x = W - 32
    for color, label, val in reversed(items):
        val_s = f"{val:,}"
        w_val = text_w(val_s, 13, True)
        w_lab = text_w(label + " ", 13)
        o.append(f'<text x="{x}" y="50" font-size="13" text-anchor="end" fill="{MUTED}">{label} '
                 f'<tspan font-weight="700" fill="{TEXT}">{val_s}</tspan></text>')
        x -= w_val + w_lab + 16
        o.append(f'<rect x="{x}" y="40" width="11" height="11" rx="3" fill="{color}"/>')
        x -= 22

    # KPIs (right-aligned): pull requests, stars
    x = W - 32
    star_txt = f"{d['total_stars']:,} stars earned"
    o.append(f'<text x="{x}" y="86" font-size="13" text-anchor="end" fill="{MUTED}">'
             f'<tspan font-weight="700" fill="{TEXT}">{d["total_stars"]:,}</tspan> stars earned</text>')
    x -= text_w(star_txt, 13) + 16
    o.append(f'<polygon points="{star_points(x, 81, 7)}" fill="{GOLD}"/>')
    x -= 24
    pr_txt = f"{prs:,} pull requests"
    o.append(f'<text x="{x}" y="86" font-size="13" text-anchor="end" fill="{MUTED}">'
             f'<tspan font-weight="700" fill="{TEXT}">{prs:,}</tspan> pull requests</text>')
    x -= text_w(pr_txt, 13) + 16
    o.append(pr_icon(x, 81, TEAL))

    # grid baseline + average line
    o.append(f'<line x1="{x0}" y1="{base + .5}" x2="{x1}" y2="{base + .5}" stroke="{BORDER}"/>')
    if total:
        ay = base - avg * scale
        o.append(f'<line class="fade" style="animation-delay:1s" x1="{x0}" y1="{ay:.1f}" x2="{x1 + 6}" '
                 f'y2="{ay:.1f}" stroke="{FAINT}" stroke-dasharray="3 5"/>')
        o.append(f'<text class="fade" style="animation-delay:1s" x="{W - 32}" y="{ay - 4:.1f}" font-size="11" '
                 f'text-anchor="end" fill="{FAINT}">avg</text>')
        o.append(f'<text class="fade" style="animation-delay:1s" x="{W - 32}" y="{ay + 12:.1f}" font-size="12" '
                 f'font-weight="700" text-anchor="end" fill="{MUTED}">{avg:.0f}/mo</text>')

    peak_i = totals.index(max(totals)) if total else -1
    for i, mo in enumerate(months):
        cx = x0 + slot * i + slot / 2
        bx = cx - bw / 2
        t = totals[i]
        delay = f"animation-delay:{0.06 * i:.2f}s"
        if t:
            h = max(3, t * scale)
            y = base - h
            top_color = LIME if mo["private"] else MINT
            o.append(f'<g class="grow" style="{delay}">')
            o.append(f'<path d="{bar_path(bx, y, bw, h, 6)}" fill="{top_color}"/>')
            if mo["private"] and mo["public"]:
                ph = max(2, mo["public"] * scale)
                o.append(f'<rect x="{bx}" y="{base - ph:.1f}" width="{bw}" height="{ph:.1f}" fill="{MINT}"/>')
            o.append('</g>')
            o.append(f'<text class="fade" style="animation-delay:{0.06 * i + .5:.2f}s" x="{cx:.1f}" '
                     f'y="{y - 8:.1f}" font-size="13" font-weight="700" text-anchor="middle" fill="{TEXT}">{t}</text>')
            if i == peak_i:
                py = y - 40
                o.append(f'<g class="pop" style="animation-delay:1.1s">'
                         f'<rect x="{cx - 21:.1f}" y="{py:.1f}" width="42" height="18" rx="9" fill="{LIME}"/>'
                         f'<text x="{cx:.1f}" y="{py + 13:.1f}" font-size="11" font-weight="800" '
                         f'text-anchor="middle" fill="{DEEP}">peak</text></g>')
        else:
            o.append(f'<rect x="{bx}" y="{base - 2}" width="{bw}" height="2" rx="1" fill="{GRID}"/>')
        o.append(f'<text x="{cx:.1f}" y="324" font-size="12" text-anchor="middle" fill="{MUTED}">'
                 f'{MONTHS[mo["m"] - 1]}</text>')
        if i == 0 or mo["m"] == 1:
            o.append(f'<text x="{cx:.1f}" y="340" font-size="11" text-anchor="middle" fill="{FAINT}">'
                     f'{mo["y"]}</text>')

    # activity lanes: pull requests (bubbles) and new stars
    o.append(f'<line x1="32" y1="356.5" x2="{W - 32}" y2="356.5" stroke="{GRID}"/>')
    max_pr = max((mo["prs"] for mo in months), default=0) or 1
    lane_y = 384
    o.append(pr_icon(W - 44, lane_y, TEAL))
    for i, mo in enumerate(months):
        cx = x0 + slot * i + slot / 2
        if mo["prs"]:
            op = 0.35 + 0.65 * mo["prs"] / max_pr
            o.append(f'<g class="pop" style="animation-delay:{1 + 0.05 * i:.2f}s">'
                     f'<circle cx="{cx:.1f}" cy="{lane_y}" r="12" fill="{TEAL}" fill-opacity="{op:.2f}" '
                     f'stroke="{TEAL}"/>'
                     f'<text x="{cx:.1f}" y="{lane_y + 4}" font-size="11" font-weight="700" '
                     f'text-anchor="middle" fill="{TEXT}">{mo["prs"]}</text></g>')
        else:
            o.append(f'<circle cx="{cx:.1f}" cy="{lane_y}" r="2.5" fill="{BORDER}"/>')
    if has_star_row:
        sy = 418
        o.append(f'<polygon points="{star_points(W - 44, sy, 7)}" fill="{GOLD}"/>')
        for i, mo in enumerate(months):
            cx = x0 + slot * i + slot / 2
            if mo["stars"]:
                o.append(f'<g class="pop" style="animation-delay:{1.4 + 0.05 * i:.2f}s">'
                         f'<polygon class="twinkle" style="animation-delay:{0.3 * i:.1f}s" '
                         f'points="{star_points(cx - 7, sy, 8)}" fill="{GOLD}"/>'
                         f'<text x="{cx + 5:.1f}" y="{sy + 4}" font-size="12" font-weight="700" '
                         f'fill="{GOLD}">+{mo["stars"]}</text></g>')
            else:
                o.append(f'<circle cx="{cx:.1f}" cy="{sy}" r="2.5" fill="{BORDER}"/>')
    o.append("</svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ languages card
def render_languages(d):
    weights = d["languages"]
    total = sum(weights.values()) or 1
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    top = ranked[:5]
    rest = sum(v for _, v in ranked[5:])
    items = [(name, v / total * 100, LANG_COLORS[i]) for i, (name, v) in enumerate(top)]
    if rest:
        items.append(("Other", rest / total * 100, OTHER_COLOR))

    W = 860
    rows = math.ceil(len(items) / 2)
    list_y0 = 146
    chip_y = list_y0 + rows * 38 + 18
    H = chip_y + 34

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'role="img" aria-label="Languages weighted by my commits">', STYLE,
         f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{CARD}" stroke="{BORDER}"/>',
         f'<text x="32" y="54" font-size="24" font-weight="800" fill="{TEXT}">Languages</text>',
         f'<text x="32" y="80" font-size="14" fill="{MUTED}">weighted by my commits · '
         f'{window_label(d["months"])}</text>',
         '<defs><clipPath id="bar"><rect x="32" y="102" width="796" height="12" rx="6"/></clipPath></defs>',
         f'<rect x="32" y="102" width="796" height="12" rx="6" fill="{GRID}"/>',
         '<g clip-path="url(#bar)"><g class="growx">']
    x = 32.0
    for name, pct, color in items:
        w = 796 * pct / 100
        o.append(f'<rect x="{x:.1f}" y="102" width="{w + .6:.1f}" height="12" fill="{color}"/>')
        x += w
    o.append('</g></g>')

    col_w, cols = 382, (32, 446)
    for k, (name, pct, color) in enumerate(items):
        cx, ry = cols[k % 2], list_y0 + (k // 2) * 38
        delay = f"animation-delay:{0.3 + 0.08 * k:.2f}s"
        o.append(f'<g class="fade" style="{delay}">'
                 f'<circle cx="{cx + 7}" cy="{ry - 5}" r="6" fill="{color}"/>'
                 f'<text x="{cx + 24}" y="{ry}" font-size="15" fill="{TEXT}">{escape(name)}</text>'
                 f'<text x="{cx + col_w}" y="{ry}" font-size="15" font-weight="700" text-anchor="end" '
                 f'fill="{TEXT}">{pct:.1f}%</text>'
                 f'<line x1="{cx}" y1="{ry + 16.5}" x2="{cx + col_w}" y2="{ry + 16.5}" stroke="{GRID}"/></g>')

    label = "also in my day-to-day"
    o.append(f'<text x="32" y="{chip_y + 4}" font-size="13" fill="{MUTED}">{label}</text>')
    x = 32 + text_w(label, 13) + 18
    chip_colors = [LIME, MINT, GOLD, TEAL, FOREST]
    for k, tool in enumerate(DAY_TO_DAY):
        color = chip_colors[k % len(chip_colors)]
        w = text_w(tool, 12, True) + 34
        o.append(f'<g class="pop" style="animation-delay:{0.8 + 0.08 * k:.2f}s">'
                 f'<rect x="{x:.1f}" y="{chip_y - 13}" width="{w:.1f}" height="26" rx="13" fill="none" '
                 f'stroke="{color}" stroke-opacity=".55"/>'
                 f'<circle cx="{x + 13:.1f}" cy="{chip_y}" r="3.5" fill="{color}"/>'
                 f'<text x="{x + 22:.1f}" y="{chip_y + 4}" font-size="12" font-weight="700" '
                 f'fill="{color}">{escape(tool)}</text></g>')
        x += w + 10
    o.append("</svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ footer
def render_footer():
    W, H = 860, 96
    layers = [  # (base y, amplitude, waves per width, seconds, reverse, top color, bottom color, opacity)
        (40, 10, 1, 14, False, DEEP, "#0b2f27", 1),
        (52, 9, 2, 10, True, FOREST, DEEP, .9),
        (64, 7, 1, 7, False, LIME, TEAL, .85),
    ]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'role="img" aria-label="">',
         "<style>.wave{animation:slide linear infinite}.rev{animation-direction:reverse}"
         f"@keyframes slide{{from{{transform:translateX(0)}}to{{transform:translateX(-{W}px)}}}}"
         "@media (prefers-reduced-motion:reduce){.wave{animation:none}}</style><defs>"]
    for k, (_, _, _, _, _, c1, c2, _) in enumerate(layers):
        o.append(f'<linearGradient id="w{k}" x1="0" y1="0" x2="0" y2="1">'
                 f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>')
    o.append(f'<clipPath id="round"><rect width="{W}" height="{H}" rx="12"/></clipPath></defs>')
    o.append('<g clip-path="url(#round)">')
    for k, (base, amp, waves, secs, rev, _, _, op) in enumerate(layers):
        pts = []
        for xx in range(0, 2 * W + 1, 10):
            yy = base + amp * math.sin(2 * math.pi * waves * xx / W + k)
            pts.append(f"{xx} {yy:.1f}")
        d_attr = "M" + " L".join(pts) + f" V{H} H0 Z"
        cls = "wave rev" if rev else "wave"
        o.append(f'<path class="{cls}" style="animation-duration:{secs}s" d="{d_attr}" '
                 f'fill="url(#w{k})" fill-opacity="{op}"/>')
    o.append("</g></svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ main
def write(name, svg):
    path = os.path.join(OUT_DIR, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(svg)
    os.replace(tmp, path)
    print(f"Wrote {path}")


def main():
    now = datetime.now(timezone.utc)
    if DEMO:
        data = demo_data(now)
    else:
        if not LOGIN or not TOKEN:
            sys.exit("GH_LOGIN and GH_TOKEN must be set")
        data = fetch(now)
    # render everything first, then write, so a failure never leaves half-updated cards
    cards = {"commits.svg": render_commits(data), "languages.svg": render_languages(data),
             "footer.svg": render_footer()}
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, svg in cards.items():
        write(name, svg)


if __name__ == "__main__":
    main()
