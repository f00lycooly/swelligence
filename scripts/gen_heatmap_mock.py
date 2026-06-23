#!/usr/bin/env python3
"""Generate 'best sport' heatmap + condensed medallion mockups for the companion."""
import os

OUT = os.path.join(os.path.dirname(__file__), "..",
                   ".superpowers/brainstorm/54517-1782220310/content/card-bestsport.html")
C = {"epic": "#1f9d57", "great": "#5cb85c", "good": "#9bcf5f", "marg": "#f0a83d", "poor": "#e8593a"}
ICON = {"kitesurf": "i-kite", "wingfoil": "i-wing", "surf": "i-surf", "sup": "i-sup", "wake": "i-wake"}
LABEL = {"kitesurf": "Kite", "wingfoil": "Wing", "surf": "Surf", "sup": "SUP", "wake": "Wake"}

def band(s):
    return "epic" if s >= 85 else "great" if s >= 70 else "good" if s >= 55 else "marg" if s >= 35 else "poor"

def windscore(w, lo, ideal, mx):
    if w < lo: return max(0, 40 * w / lo)
    if w > mx: return 0
    if w <= ideal: return 60 + 40 * (w - lo) / (ideal - lo)
    return 100 - 40 * (w - ideal) / (mx - ideal)

def surfscore(w, h):
    sf = (0.4 * h / 0.6) if h < 0.6 else (0.6 + 0.4 * (h - 0.6) / 0.9 if h <= 1.5 else max(0, 1 - (h - 1.5) / 2))
    wp = 1.0 if w <= 8 else (max(0.1, 1 - (w - 8) / 14) if w < 22 else 0.1)
    return 100 * min(1, sf) * wp

def flatscore(w, h, k=7):
    return max(0, 100 - w * k - max(0, (h - 0.4)) * 60)

SPORTS = {  # per-spot sport set (enabled subset)
    "Christchurch Hbr": ("sheltered", ["wingfoil", "sup"]),
    "Avon Beach": ("sea", ["kitesurf", "surf", "sup"]),
    "Bournemouth Pier": ("sea", ["surf"]),
    "Sandbanks": ("sea", ["kitesurf", "wingfoil"]),
    "New Forest WP": ("inland", ["wake", "sup"]),
    "Hurst / Keyhaven": ("sea", ["kitesurf", "wingfoil"]),
}

def score(sport, w, h, water):
    if sport == "kitesurf": return windscore(w, 12, 20, 35)
    if sport == "wingfoil": return windscore(w, 10, 16, 33)
    if sport == "surf": return surfscore(w, h)
    if sport == "sup": return flatscore(w, 0 if water != "sea" else h, 7)
    if sport == "wake": return flatscore(w, 0, 6)
    return 0

def best_sport(spot, w, h):
    water, sports = SPORTS[spot]
    bs, bsc = None, -1
    for sp in sports:
        s = score(sp, w, h, water)
        if s > bsc: bs, bsc = sp, s
    return bs, round(bsc)

# ---- Heatmap scenario: 4 days × 4 windows (06-10,10-14,14-18,18-22) ----
WINDOWS = ["06–10", "10–14", "14–18", "18–22"]
DAYS_H = ["Sat", "Sun", "Mon", "Tue"]
# (wind kn, swell m) per day per window
COND = {
    "Sat": [(12, 1.0), (20, 1.2), (26, 1.4), (18, 1.2)],
    "Sun": [(6, 1.5), (9, 1.6), (12, 1.4), (8, 1.2)],
    "Mon": [(4, 0.6), (6, 0.5), (8, 0.4), (5, 0.3)],
    "Tue": [(10, 0.8), (16, 0.9), (22, 1.0), (14, 0.8)],
}

def heatmap():
    h = ['<div class="hm"><div class="hmgrid">']
    # header
    h.append('<div class="hl"></div>')
    for d in DAYS_H:
        h.append(f'<div class="dhead">{d}</div>')
    # window subheader
    h.append('<div class="hl"></div>')
    for d in DAYS_H:
        h.append('<div class="whead">' + "".join(f'<span>{w}</span>' for w in WINDOWS) + '</div>')
    # rows
    for spot in SPORTS:
        h.append(f'<div class="hl">{spot}</div>')
        for d in DAYS_H:
            h.append('<div class="wrow">')
            for wi in range(4):
                w, sw = COND[d][wi]
                sp, sc = best_sport(spot, w, sw)
                col = C[band(sc)]
                h.append(f'<div class="hcell" style="background:{col}" title="{LABEL[sp]} {sc}">'
                         f'<svg class="icon"><use href="#{ICON[sp]}"/></svg><span>{sc}</span></div>')
            h.append('</div>')
    h.append('</div></div>')
    return "".join(h)

# ---- Condensed: best sport per day (household-wide), 7 days ----
DAYS7 = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]
PEAK = [(26, 1.4, "14:00"), (12, 1.6, "11:00"), (8, 0.4, "09:00"), (22, 1.0, "15:00"),
        (15, 0.9, "13:00"), (28, 1.5, "15:00"), (10, 0.7, "10:00")]

def day_best():
    h = ['<div class="cstrip">']
    for di, d in enumerate(DAYS7):
        w, sw, t = PEAK[di]
        gb, gsc, gspot = None, -1, None
        for spot in SPORTS:
            sp, sc = best_sport(spot, w, sw)
            if sc > gsc: gb, gsc, gspot = sp, sc, spot
        col = C[band(gsc)]
        h.append(
            f'<div class="cd"><div class="cring" style="--c:{col};--p:{gsc}">'
            f'<div class="cin"><svg class="icon big"><use href="#{ICON[gb]}"/></svg></div></div>'
            f'<div class="cday">{d}</div><div class="csc" style="color:{col}">{gsc}</div>'
            f'<div class="cspot">{gspot.split(" ")[0]}</div><div class="ct">{t}</div></div>')
    h.append('</div>')
    return "".join(h)

DEFS = """
<symbol id="i-kite" viewBox="0 0 24 24"><path d="M2.5 7 Q12 1 21.5 7"/><path d="M5.5 7.6 L11 15.5"/><path d="M18.5 7.6 L13 15.5"/><path d="M10.5 15.6 H13.5"/><path d="M7 20 Q12 22.5 17 20"/></symbol>
<symbol id="i-wing" viewBox="0 0 24 24"><path d="M3.5 8 Q12 2.5 20.5 8 Q12 10.5 3.5 8 Z"/><path d="M12 10.5 L12 16"/><path d="M7.5 17.5 Q12 15.5 16.5 17.5"/></symbol>
<symbol id="i-surf" viewBox="0 0 24 24"><path d="M2 17 C6 17 6 9 11 9 C15.5 9 14 15 19.5 14"/><path d="M11 9 C13.5 7.8 14.6 10 12.4 11.6"/><path d="M13.5 20 L20 13.5"/></symbol>
<symbol id="i-sup" viewBox="0 0 24 24"><path d="M3 18 Q12 21 21 18"/><path d="M3 18 Q12 15.6 21 18"/><path d="M14.5 3.5 L9 17"/><path d="M13 3.5 H16"/><path d="M7.5 16 L9 19 L10.7 16 Z"/></symbol>
<symbol id="i-wake" viewBox="0 0 24 24"><path d="M2 18.5 q3 -1.6 6 0 t6 0 t6 0"/><path d="M5.5 16.8 L13 13.2"/><path d="M8 16.2 L8.6 14.8"/><path d="M11 15 L11.6 13.6"/><path d="M18.5 6 H21.5"/><path d="M20 6.6 L13.5 12.6"/></symbol>
"""

HTML = f"""<div id="sw-bs">
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Saira+Condensed:wght@500;600;700&display=swap');
#sw-bs{{ --card:#1b1e25; --line:#2a2e38; --ink:#e7e9ee; --dim:#878e9c; background:#14161b; color:var(--ink);
  font-family:'Outfit',sans-serif; padding:26px 18px 70px; min-height:100vh; box-sizing:border-box;}}
#sw-bs *{{ box-sizing:border-box;}}
.h1{{ font-family:'Saira Condensed'; font-weight:700; letter-spacing:.14em; text-transform:uppercase; font-size:14px; color:#7f8694; margin:0 0 6px;}}
.lead{{ color:#aab0bd; font-size:14px; max-width:860px; line-height:1.5; margin:0 0 24px;}}
.sec{{ max-width:980px; margin:0 auto 36px;}}
.ctitle{{ display:flex; align-items:baseline; gap:10px; margin:0 2px 12px; flex-wrap:wrap;}}
.ctitle .tag{{ font-family:'Saira Condensed'; font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:12px; color:#8b93a3; background:#23262e; padding:3px 9px; border-radius:6px;}}
.ctitle .nm{{ font-size:16px; color:#dfe3ea; font-weight:600;}} .ctitle .ds{{ font-size:12.5px; color:var(--dim);}}
.card{{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px 16px; overflow-x:auto;}}
svg.icon{{ width:17px; height:17px; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round;}}
svg.icon.big{{ width:24px; height:24px;}}
.choose button{{ font-family:'Saira Condensed'; letter-spacing:.08em; text-transform:uppercase; font-size:12px; background:#23262e; color:#cdd2dc; border:1px solid #343843; border-radius:20px; padding:7px 16px; cursor:pointer; margin-top:12px;}}

/* heatmap */
.hmgrid{{ display:grid; grid-template-columns:130px repeat(4,1fr); gap:6px; min-width:720px;}}
.dhead{{ text-align:center; font-weight:700; font-size:13px; color:#dfe3ea; border-bottom:1px solid var(--line); padding-bottom:4px;}}
.whead{{ display:grid; grid-template-columns:repeat(4,1fr);}}
.whead span{{ text-align:center; font-size:9px; color:var(--dim);}}
.hl{{ font-size:12px; color:#cfd4de; display:flex; align-items:center; font-weight:500;}}
.wrow{{ display:grid; grid-template-columns:repeat(4,1fr); gap:3px;}}
.hcell{{ height:38px; border-radius:6px; color:#06140f; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:1px;}}
.hcell span{{ font-weight:800; font-size:11px; line-height:1;}}
.hcell svg{{ width:15px; height:15px;}}

/* condensed best-of-day */
.cstrip{{ display:flex; gap:8px; justify-content:space-between; min-width:640px;}}
.cd{{ flex:1; text-align:center;}}
.cring{{ width:56px; height:56px; border-radius:50%; margin:0 auto 5px; position:relative;
  background:conic-gradient(var(--c) calc(var(--p)*1%), #2a2e38 0);}}
.cring::after{{ content:''; position:absolute; inset:4px; border-radius:50%; background:var(--card);}}
.cin{{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; z-index:1; color:#e7e9ee;}}
.cday{{ font-size:11px; color:#cfd4de; font-weight:600;}}
.csc{{ font-weight:800; font-size:14px; line-height:1;}}
.cspot{{ font-size:10px; color:#aab0bd;}} .ct{{ font-size:9.5px; color:var(--dim);}}
</style>
<svg width="0" height="0" style="position:absolute"><defs>{DEFS}</defs></svg>

<div class="h1">Swelligence · best-sport views</div>
<p class="lead">Two "what's the best call" views. The heatmap answers <b>where & when</b> (each cell = the best
sport for that location in that 4-hour window, coloured by how good). The condensed strip answers
<b>what this week</b> (each day's single best opportunity across all spots). Synthesised conditions.</p>

<div class="sec">
  <div class="ctitle"><span class="tag">H</span><span class="nm">Best-Sport Heatmap</span><span class="ds">— Windy-style: rows = locations, columns = 4-hour windows; cell shows the best sport + score</span></div>
  <div class="card">{heatmap()}</div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Heatmap')">Choose Heatmap</button></div>
</div>

<div class="sec">
  <div class="ctitle"><span class="tag">D</span><span class="nm">Best-of-Day Medallions</span><span class="ds">— condensed: one ring per day, sport icon in the centre = the best sport that day (+ spot & time)</span></div>
  <div class="card">{day_best()}</div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('BestOfDay')">Choose Best-of-Day</button></div>
</div>

</div>
"""
with open(OUT, "w") as f:
    f.write(HTML)
print("wrote", os.path.normpath(OUT), len(HTML), "bytes")
