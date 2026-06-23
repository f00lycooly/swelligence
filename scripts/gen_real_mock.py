#!/usr/bin/env python3
"""Pull REAL get_forecast data from live HA and render opportunity-first mockups."""
import json, os, sys, urllib.request

HA_URL, TOKEN = sys.argv[1], sys.argv[2]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
OUT = os.path.join(os.path.dirname(__file__), "..",
                   ".superpowers/brainstorm/54517-1782220310/content/card-real.html")
C = {"epic": "#1f9d57", "great": "#5cb85c", "good": "#9bcf5f", "marg": "#f0a83d", "poor": "#e8593a"}
ICON = {"kitesurf": "i-kite", "wingfoil": "i-wing", "windsurf": "i-windsurf", "surf": "i-surf",
        "sup": "i-sup", "sailing": "i-sail", "seaswim": "i-swim",
        "wakeboard_inland": "i-wake", "wakeboard_sea": "i-wake"}
GOOD, MARG = 55, 35

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(HA_URL + path, data=data, headers=H, method=method)
    with urllib.request.urlopen(r, timeout=40) as resp:
        return json.loads(resp.read().decode())

def band(s):
    return "epic" if s >= 85 else "great" if s >= 70 else "good" if s >= 55 else "marg" if s >= 35 else "poor"

# --- gather entities + hourly forecasts ---
states = req("GET", "/api/states")
ents = [s for s in states if s["entity_id"].startswith("sensor.swelligence_")
        and s["entity_id"].endswith("_suitability")]
data = {}  # entity -> {spot, sport, forecast[]}
for s in ents:
    eid = s["entity_id"]
    r = req("POST", "/api/services/swelligence/get_forecast?return_response",
            {"entity_id": eid, "type": "hourly"})
    resp = r.get("service_response", {}).get(eid)
    if resp:
        data[eid] = resp

# --- compute contiguous "sessions" (runs of score>=GOOD) per entity ---
def hour(dt): return int(dt[11:13])
def dayk(dt): return dt[:10]

sessions = []  # {spot, sport, day, start, end, peak, verdict, kit}
for eid, v in data.items():
    fc = sorted(v["forecast"], key=lambda x: x["datetime"])
    run = []
    def flush(run):
        if not run: return
        peak = max(run, key=lambda x: x["score"])
        sessions.append({
            "spot": v["spot"], "sport": v["sport"], "day": dayk(run[0]["datetime"]),
            "start": hour(run[0]["datetime"]), "end": hour(run[-1]["datetime"]) + 1,
            "peak": round(peak["score"]), "verdict": band(peak["score"]),
            "kit": (f'{peak.get("kit_rig_m2"):g}m²' if peak.get("kit_rig_m2") else ""),
            "time": peak["datetime"][11:16],
        })
    prev_h, prev_d = None, None
    for p in fc:
        if p["score"] is None:
            continue
        hh, dd = hour(p["datetime"]), dayk(p["datetime"])
        if p["score"] >= GOOD:
            if run and (hh != prev_h + 1 or dd != prev_d):
                flush(run); run = []
            run.append(p); prev_h, prev_d = hh, dd
        else:
            flush(run); run = []; prev_h, prev_d = None, None
    flush(run)

sessions.sort(key=lambda s: (s["day"], s["start"], -s["peak"]))

# --- best per day (any sport/spot) for medallions ---
days = sorted({dayk(p["datetime"]) for v in data.values() for p in v["forecast"]})[:7]
def wd(d):
    import datetime as _dt
    return _dt.date.fromisoformat(d).strftime("%a")
best_day = []
for d in days:
    best = None
    for v in data.values():
        for p in v["forecast"]:
            if dayk(p["datetime"]) == d and p["score"] is not None:
                if best is None or p["score"] > best["s"]:
                    best = {"s": p["score"], "sport": v["sport"], "spot": v["spot"], "t": p["datetime"][11:16],
                            "kit": (f'{p.get("kit_rig_m2"):g}m²' if p.get("kit_rig_m2") else "")}
    best_day.append({"day": wd(d), **best})

# --- opportunity timeline: per spot, sessions placed on a day grid ---
spots = []
for v in data.values():
    if v["spot"] not in spots: spots.append(v["spot"])

# ============ render ============
def medallions():
    h = ['<div class="cstrip">']
    for b in best_day:
        col = C[band(b["s"])]; v = band(b["s"])
        faded = "faded" if b["s"] < MARG else ""
        h.append(
            f'<div class="cd {faded}"><div class="cring" style="--c:{col};--p:{b["s"]}">'
            f'<div class="cin"><div class="cscore" style="color:{col}">{round(b["s"])}</div>'
            f'<svg class="icon sm"><use href="#{ICON.get(b["sport"],"i-kite")}"/></svg></div></div>'
            f'<div class="cday">{b["day"]}</div>'
            f'<div class="cspot">{b["spot"].split(" ")[0]}{(" · "+b["kit"]) if b["kit"] else ""}</div>'
            f'<div class="ct">{b["t"]}</div></div>')
    h.append('</div>')
    return "".join(h)

def agenda():
    goods = [s for s in sessions if s["peak"] >= GOOD]
    if not goods:
        return '<div class="empty">No sessions above "good" in the next 7 days — it\'s quiet. ' \
               'A real agenda only lists worth-going windows; nothing to show beats showing rubbish.</div>'
    h = ['<div class="agenda">']
    last = None
    for s in goods[:14]:
        if s["day"] != last:
            h.append(f'<div class="aday">{wd(s["day"])} {s["day"][8:10]}</div>'); last = s["day"]
        col = C[s["verdict"]]
        h.append(
            f'<div class="arow"><div class="awhen">{s["start"]:02d}–{s["end"]:02d}</div>'
            f'<svg class="icon" style="color:{col}"><use href="#{ICON.get(s["sport"],"i-kite")}"/></svg>'
            f'<div class="aspot">{s["spot"]}</div>'
            f'<div class="akit">{s["kit"]}</div>'
            f'<div class="achip" style="background:{col}">{s["peak"]}</div></div>')
    h.append('</div>')
    return "".join(h)

def timeline():
    h = ['<div class="tl">']
    h.append('<div class="tlhead"><div class="tlspot"></div>' +
             "".join(f'<div class="tlday">{wd(d)}</div>' for d in days) + '</div>')
    for spot in spots:
        h.append(f'<div class="tlrow"><div class="tlspot">{spot.split(" / ")[0]}</div>')
        for d in days:
            h.append('<div class="tlcell">')
            ss = [s for s in sessions if s["spot"] == spot and s["day"] == d and s["peak"] >= GOOD]
            for s in ss:
                left = max(0, (s["start"] - 5) / 18 * 100)
                width = max(8, (s["end"] - s["start"]) / 18 * 100)
                col = C[s["verdict"]]
                h.append(f'<div class="blk" style="left:{left}%;width:{width}%;background:{col}" '
                         f'title="{s["start"]}-{s["end"]} {s["sport"]} {s["peak"]}">'
                         f'<svg class="icon xs"><use href="#{ICON.get(s["sport"],"i-kite")}"/></svg></div>')
            h.append('</div>')
        h.append('</div>')
    h.append('</div>')
    return "".join(h)

DEFS = """
<symbol id="i-kite" viewBox="0 0 24 24"><path d="M2.5 7 Q12 1 21.5 7"/><path d="M5.5 7.6 L11 15.5"/><path d="M18.5 7.6 L13 15.5"/><path d="M10.5 15.6 H13.5"/><path d="M7 20 Q12 22.5 17 20"/></symbol>
<symbol id="i-windsurf" viewBox="0 0 24 24"><path d="M3 19.5 Q12 22.5 21 19.5"/><path d="M12 19 L12 3.5"/><path d="M12 4 Q20 9.5 12 15"/><path d="M12 9.5 L17.5 9"/></symbol>
<symbol id="i-wing" viewBox="0 0 24 24"><path d="M3.5 8 Q12 2.5 20.5 8 Q12 10.5 3.5 8 Z"/><path d="M12 10.5 L12 16"/><path d="M7.5 17.5 Q12 15.5 16.5 17.5"/></symbol>
<symbol id="i-surf" viewBox="0 0 24 24"><path d="M2 17 C6 17 6 9 11 9 C15.5 9 14 15 19.5 14"/><path d="M11 9 C13.5 7.8 14.6 10 12.4 11.6"/><path d="M13.5 20 L20 13.5"/></symbol>
<symbol id="i-sup" viewBox="0 0 24 24"><path d="M3 18 Q12 21 21 18"/><path d="M3 18 Q12 15.6 21 18"/><path d="M14.5 3.5 L9 17"/><path d="M13 3.5 H16"/><path d="M7.5 16 L9 19 L10.7 16 Z"/></symbol>
<symbol id="i-sail" viewBox="0 0 24 24"><path d="M4 18 L20 18 L17.5 21 H6.5 Z"/><path d="M12 18 L12 3.5"/><path d="M12.8 5 L18.5 16 H12.8 Z"/><path d="M11.2 6.5 L6 16 H11.2 Z"/></symbol>
<symbol id="i-swim" viewBox="0 0 24 24"><circle cx="8" cy="8.5" r="2"/><path d="M9.6 10 Q14 8.4 17.5 11.5"/><path d="M9.6 10 Q11.5 5.5 15 7.5"/><path d="M2 18 q2.6 -2 5.2 0 t5.2 0 t5.2 0"/></symbol>
<symbol id="i-wake" viewBox="0 0 24 24"><path d="M2 18.5 q3 -1.6 6 0 t6 0 t6 0"/><path d="M5.5 16.8 L13 13.2"/><path d="M8 16.2 L8.6 14.8"/><path d="M11 15 L11.6 13.6"/><path d="M18.5 6 H21.5"/><path d="M20 6.6 L13.5 12.6"/></symbol>
"""

HTML = f"""<div id="sw-r">
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Saira+Condensed:wght@500;600;700&display=swap');
#sw-r{{ --card:#1b1e25; --line:#2a2e38; --ink:#e7e9ee; --dim:#878e9c; background:#14161b; color:var(--ink);
  font-family:'Outfit',sans-serif; padding:26px 18px 70px; min-height:100vh; box-sizing:border-box;}}
#sw-r *{{ box-sizing:border-box;}}
.h1{{ font-family:'Saira Condensed'; font-weight:700; letter-spacing:.14em; text-transform:uppercase; font-size:14px; color:#7f8694; margin:0 0 6px;}}
.lead{{ color:#aab0bd; font-size:14px; max-width:880px; line-height:1.5; margin:0 0 6px;}}
.real{{ display:inline-block; font-size:11px; color:#0c1a12; background:#5cb85c; border-radius:10px; padding:2px 9px; font-weight:700; margin:0 0 22px;}}
.sec{{ max-width:880px; margin:0 auto 36px;}}
.ctitle{{ display:flex; align-items:baseline; gap:10px; margin:0 2px 12px; flex-wrap:wrap;}}
.ctitle .tag{{ font-family:'Saira Condensed'; font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:12px; color:#8b93a3; background:#23262e; padding:3px 9px; border-radius:6px;}}
.ctitle .nm{{ font-size:16px; color:#dfe3ea; font-weight:600;}} .ctitle .ds{{ font-size:12.5px; color:var(--dim);}}
.card{{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; overflow-x:auto;}}
svg.icon{{ width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round;}}
svg.icon.sm{{ width:15px; height:15px;}} svg.icon.xs{{ width:13px; height:13px;}}
.choose button{{ font-family:'Saira Condensed'; letter-spacing:.08em; text-transform:uppercase; font-size:12px; background:#23262e; color:#cdd2dc; border:1px solid #343843; border-radius:20px; padding:7px 16px; cursor:pointer; margin-top:12px;}}
.empty{{ color:#aab0bd; font-size:13.5px; line-height:1.5;}}

/* punchier medallions */
.cstrip{{ display:flex; gap:8px; justify-content:space-between; min-width:620px;}}
.cd{{ flex:1; text-align:center;}} .cd.faded{{ opacity:.5;}}
.cring{{ width:66px; height:66px; border-radius:50%; margin:0 auto 6px; position:relative;
  background:conic-gradient(var(--c) calc(var(--p)*1%), #2a2e38 0);}}
.cring::after{{ content:''; position:absolute; inset:5px; border-radius:50%; background:#0f1115;}}
.cin{{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; z-index:1; gap:0;}}
.cscore{{ font-family:'Saira Condensed'; font-weight:700; font-size:26px; line-height:.8;}}
.cin .icon{{ color:#aab0bd; margin-top:1px;}}
.cday{{ font-size:12px; color:#e7e9ee; font-weight:700;}}
.cspot{{ font-size:10.5px; color:#aab0bd;}} .ct{{ font-size:9.5px; color:var(--dim);}}

/* agenda */
.agenda{{ display:flex; flex-direction:column;}}
.aday{{ font-family:'Saira Condensed'; letter-spacing:.08em; text-transform:uppercase; font-size:11px; color:var(--dim); margin:12px 0 5px; }}
.aday:first-child{{ margin-top:0;}}
.arow{{ display:flex; align-items:center; gap:11px; padding:8px 4px; border-bottom:1px solid var(--line);}}
.awhen{{ font-family:'Saira Condensed'; font-weight:600; font-size:14px; width:58px; color:#cfd4de;}}
.aspot{{ flex:1; font-size:13.5px; color:#e7e9ee; font-weight:500;}}
.akit{{ font-size:11px; color:var(--dim);}}
.achip{{ font-family:'Saira Condensed'; font-weight:700; font-size:14px; color:#06140f; border-radius:9px; padding:3px 11px; min-width:38px; text-align:center;}}

/* timeline */
.tl{{ min-width:680px;}}
.tlhead, .tlrow{{ display:grid; grid-template-columns:120px repeat({len(days)},1fr); gap:5px; align-items:center;}}
.tlhead{{ margin-bottom:6px;}}
.tlday{{ text-align:center; font-size:11px; color:var(--dim); font-weight:600;}}
.tlspot{{ font-size:12px; color:#cfd4de; font-weight:500;}}
.tlrow{{ margin-bottom:5px;}}
.tlcell{{ position:relative; height:26px; background:#11141b; border:1px solid var(--line); border-radius:5px;}}
.blk{{ position:absolute; top:2px; bottom:2px; border-radius:4px; display:flex; align-items:center; justify-content:center; color:#06140f;}}
</style>
<svg width="0" height="0" style="position:absolute"><defs>{DEFS}</defs></svg>

<div class="h1">Swelligence · opportunity-first views (LIVE DATA)</div>
<p class="lead">Rebuilt with your <b>real</b> 7-day forecast pulled from the live integration just now ({len(data)} sensors).
The new idea: surface only the sessions worth going (score ≥ {GOOD}); stop rendering "best of a bad lot".</p>
<div class="real">● live get_forecast data</div>

<div class="sec">
  <div class="ctitle"><span class="tag">D</span><span class="nm">Best-of-Day Medallions — punchier</span><span class="ds">score is the hero; faded = nothing decent that day</span></div>
  <div class="card">{medallions()}</div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Medallions-v2')">Choose Medallions v2</button></div>
</div>

<div class="sec">
  <div class="ctitle"><span class="tag">A</span><span class="nm">Session Agenda</span><span class="ds">— only the go-worthy windows, chronological. The easiest to read.</span></div>
  <div class="card">{agenda()}</div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Agenda')">Choose Agenda</button></div>
</div>

<div class="sec">
  <div class="ctitle"><span class="tag">T</span><span class="nm">Opportunity Timeline</span><span class="ds">— per spot, the week; coloured blocks ONLY where there's a good session (icon = sport). Empty = nothing on.</span></div>
  <div class="card">{timeline()}</div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Timeline')">Choose Timeline</button></div>
</div>

</div>
"""
with open(OUT, "w") as f:
    f.write(HTML)
print("wrote", os.path.normpath(OUT), len(HTML), "bytes;", len(data), "sensors;",
      len([s for s in sessions if s['peak'] >= GOOD]), "good+ sessions")
