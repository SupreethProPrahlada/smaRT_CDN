"""HTML route map (Sprint 4, Developer 2).

Reads results/live_routes.json (written by the controller every second) and
writes results/route_map.html: the topology with each path coloured by state
and utilization, srv1's active path highlighted, and the live client flows.
The page reloads itself, so leave it open in a browser while this runs.

    uv run python scripts/route_map.py            # refresh every second
    uv run python scripts/route_map.py --once     # write the page once
"""

import argparse
import html
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.settings import LIVE_ROUTES_JSON, SERVERS

ROUTE_MAP_HTML = "results/route_map.html"
STALE_AFTER = 5.0

# Node positions in the SVG.
NODES = {
    "clients": (70, 210), "s1": (230, 210), "s5": (380, 60),
    "s2": (530, 110), "s3": (530, 210), "s4": (530, 310),
    "srv1": (700, 110), "srv2": (700, 210), "srv3": (700, 310), "bg": (530, 30),
}


def _link_class(status, utilization):
    if status != "UP":
        return "down"
    if utilization >= 0.8:
        return "hot"
    if utilization >= 0.5:
        return "warm"
    return "ok"


def _fmt_rtt(value):
    return "-" if value is None else f"{float(value):.1f} ms"


def _edge(a, b, cls, label="", active=False):
    (x1, y1), (x2, y2) = NODES[a], NODES[b]
    width = 6 if active else 3
    out = f'<line class="link {cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke-width="{width}"/>'
    if label:
        out += f'<text class="label" x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 8}">{html.escape(label)}</text>'
    return out


def _node(name, cls, sub=""):
    x, y = NODES[name]
    out = (f'<g class="node {cls}"><rect x="{x - 42}" y="{y - 18}" width="84" height="36" rx="8"/>'
           f'<text x="{x}" y="{y + 5}">{html.escape(name)}</text></g>')
    if sub:
        out += f'<text class="sub" x="{x}" y="{y + 34}">{html.escape(sub)}</text>'
    return out


def render_html(data, now=None):
    """Return the route-map page for one live_routes.json snapshot."""
    now = time.time() if now is None else now
    servers = data.get("servers", {})
    paths = data.get("paths", {})
    active = data.get("srv1_path", "primary")
    age = now - float(data.get("timestamp", 0) or 0)

    def server(name):
        return servers.get(name, {})

    def path(name):
        return paths.get(name, {"status": "DOWN", "utilization": 0.0})

    primary, detour = path("primary"), path("detour")
    svg = [
        _edge("clients", "s1", "ok"),
        _edge("s1", "s2", _link_class(primary.get("status"), primary.get("utilization", 0)),
              f"primary {_fmt_rtt(primary.get('rtt_ms'))} · {primary.get('utilization', 0) * 100:.0f}%",
              active == "primary"),
        _edge("s1", "s5", _link_class(detour.get("status"), detour.get("utilization", 0)),
              f"detour {_fmt_rtt(detour.get('rtt_ms'))} · {detour.get('utilization', 0) * 100:.0f}%",
              active == "detour"),
        _edge("s5", "s2", _link_class(detour.get("status"), detour.get("utilization", 0)), "", active == "detour"),
        _edge("s2", "bg", "ok"),
    ]
    for name, switch in (("srv2", "s3"), ("srv3", "s4")):
        d = server(name)
        svg.append(_edge("s1", switch, _link_class(d.get("status"), d.get("utilization", 0)),
                         f"{_fmt_rtt(d.get('rtt_ms'))} · {d.get('utilization', 0) * 100:.0f}%"))
    for name, switch in (("srv1", "s2"), ("srv2", "s3"), ("srv3", "s4")):
        svg.append(_edge(switch, name, "ok" if server(name).get("status") == "UP" else "down"))

    svg.append(_node("clients", "host", "c1-c6"))
    for sw in ("s1", "s2", "s3", "s4", "s5"):
        svg.append(_node(sw, "switch"))
    svg.append(_node("bg", "host"))
    for name in ("srv1", "srv2", "srv3"):
        d = server(name)
        up = d.get("status") == "UP"
        svg.append(_node(name, "up" if up else "down",
                         f"{SERVERS[name]['ip']} · {d.get('active_conns', 0)} conns" if up else "DOWN"))

    rows = "".join(
        f"<tr><td>{html.escape(str(f.get('client')))}</td><td>{html.escape(str(f.get('server')))}</td>"
        f"<td>{html.escape(str(f.get('path')))}</td><td>{float(f.get('rate_mbps', 0)):.1f}</td></tr>"
        for f in data.get("flows", []))
    rows = rows or '<tr><td colspan="4" class="muted">No active flows</td></tr>'
    stale = (f'<p class="stale">Controller data is {age:.0f}s old: is the controller running?</p>'
             if age > STALE_AFTER else "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="2">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart CDN Route Map</title>
<style>
:root {{ --bg:#f7f7f5; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#d6d6d0;
  --ok:#2f8f4e; --warm:#c98a12; --hot:#c7362f; --down:#9a9a94; --sw:#3b5b8c; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161614; --fg:#ecece8; --muted:#9a9a94;
  --card:#22221f; --line:#3a3a36; --sw:#7c9fd6; }} }}
body {{ margin:0; padding:16px; font:15px/1.4 system-ui,sans-serif; background:var(--bg); color:var(--fg); }}
h1 {{ font-size:20px; margin:0 0 4px; }} .muted, .sub {{ color:var(--muted); fill:var(--muted); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; margin-top:12px; }}
svg {{ width:100%; max-width:780px; height:auto; display:block; }}
.link {{ stroke-linecap:round; }} .ok {{ stroke:var(--ok); }} .warm {{ stroke:var(--warm); }}
.hot {{ stroke:var(--hot); }} .link.down {{ stroke:var(--down); stroke-dasharray:6 6; }}
.label {{ font-size:12px; text-anchor:middle; fill:var(--fg); paint-order:stroke;
  stroke:var(--card); stroke-width:5px; stroke-linejoin:round; }} .sub {{ font-size:11px; text-anchor:middle; }}
.node text {{ text-anchor:middle; font-weight:600; fill:#fff; }}
.node rect {{ stroke:none; }} .switch rect {{ fill:var(--sw); }} .host rect {{ fill:var(--muted); }}
.up rect {{ fill:var(--ok); }} .node.down rect {{ fill:var(--hot); }}
table {{ border-collapse:collapse; width:100%; }} th, td {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--line); }}
.stale {{ color:var(--hot); font-weight:600; }}
</style></head><body>
<h1>Smart CDN Route Map</h1>
<div class="muted">Mode: {html.escape(str(data.get('cdn_mode', '?')))} · srv1 path: <strong>{html.escape(str(active))}</strong>
 · thick line = srv1's active path · green &lt;50%, amber &lt;80%, red busy, grey dashed = down</div>
{stale}
<div class="card"><svg viewBox="0 0 780 360" role="img" aria-label="Topology with live path state">{''.join(svg)}</svg></div>
<div class="card"><table><thead><tr><th>Client</th><th>Server</th><th>Path</th><th>Mbit/s</th></tr></thead>
<tbody>{rows}</tbody></table></div>
</body></html>
"""


def write_once(source=LIVE_ROUTES_JSON, target=ROUTE_MAP_HTML):
    try:
        with open(source, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    os.replace(tmp, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the live HTML route map")
    parser.add_argument("--once", action="store_true", help="write the page once and exit")
    args = parser.parse_args(argv)
    if args.once:
        write_once()
        print(f"Wrote {ROUTE_MAP_HTML}")
        return
    print(f"Writing {ROUTE_MAP_HTML} every second; open it in a browser. Ctrl+C to stop.")
    while True:
        write_once()
        time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
