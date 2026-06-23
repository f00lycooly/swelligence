#!/usr/bin/env python3
"""Generate the 7-day forecast mockup HTML for the visual companion."""
import os

OUT = os.path.join(os.path.dirname(__file__), "..",
                   ".superpowers/brainstorm/54517-1782220310/content/card-forecast.html")

C = {"epic": "#1f9d57", "great": "#5cb85c", "good": "#9bcf5f", "marg": "#f0a83d", "poor": "#e8593a"}

def band(s):
    return "epic" if s >= 85 else "great" if s >= 70 else "good" if s >= 55 else "marg" if s >= 35 else "poor"

DAYS = ["Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon"]
DATES = ["24", "25", "26", "27", "28", "29", "30"]
BEST = [66, 24, 78, 39, 23, 72, 22]
BEST_T = ["10:00", "07:00", "15:00", "13:00", "14:00", "15:00", "09:00"]
KIT = ["12m²", "14m²", "12m²", "14m²", "14m²", "12m²", "14m²"]
HOURS = list(range(6, 22))  # 06..21
HOURLY = [
    [40,52,60,66,64,58,50,44,40,36,34,30,28,26,24,22],
    [18,20,22,24,23,22,20,19,18,18,17,16,16,15,14,14],
    [44,48,52,56,60,64,68,72,76,78,74,68,60,52,46,40],
    [28,30,33,36,38,39,38,36,34,32,30,28,26,24,22,20],
    [16,18,20,22,23,22,21,20,19,18,18,17,16,15,14,14],
    [40,44,48,52,56,60,66,70,72,70,66,60,54,48,44,40],
    [16,18,20,22,21,20,19,18,18,17,16,16,15,14,14,13],
]

def ribbon():
    h = ['<div class="ribbon">']
    # time axis
    h.append('<div class="rrow axis"><div class="rlab"></div><div class="cells">')
    for hr in HOURS:
        lab = f"{hr:02d}" if hr % 3 == 0 else ""
        h.append(f'<div class="hx">{lab}</div>')
    h.append('</div></div>')
    for di, day in enumerate(DAYS):
        h.append('<div class="rrow"><div class="rlab">'
                 f'<b>{day}</b><span>{DATES[di]}</span></div><div class="cells">')
        row = HOURLY[di]
        peak = max(range(len(row)), key=lambda i: row[i])
        for i, s in enumerate(row):
            sel = " peak" if i == peak else ""
            h.append(f'<div class="hc{sel}" style="background:{C[band(s)]}" '
                     f'title="{HOURS[i]:02d}:00 · {s}"></div>')
        h.append(f'</div><div class="rbest" style="color:{C[band(BEST[di])]}">{BEST[di]}</div></div>')
    h.append('</div>')
    return "".join(h)

def medallions():
    h = ['<div class="mstrip">']
    for di, day in enumerate(DAYS):
        s = BEST[di]; col = C[band(s)]
        h.append(
            f'<div class="dm"><div class="dring" style="--c:{col};--p:{s}">'
            f'<div class="di"><div class="dd">{day}</div><div class="ds">{s}</div></div></div>'
            f'<div class="dt">{BEST_T[di]}</div><div class="dk">{KIT[di]}</div></div>')
    h.append('</div>')
    return "".join(h)

def columns():
    h = ['<div class="cols">']
    for di, day in enumerate(DAYS):
        s = BEST[di]; col = C[band(s)]
        h.append(f'<div class="cc"><div class="cbar"><div class="cfill" style="height:{s}%;background:{col}"></div></div>'
                 f'<div class="cn" style="color:{col}">{s}</div><div class="cd">{day}</div><div class="ck">{BEST_T[di]} · {KIT[di]}</div></div>')
    h.append('</div>')
    return "".join(h)

HTML = f"""<div id="sw-fc">
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Saira+Condensed:wght@500;600;700&display=swap');
#sw-fc{{ --epic:{C['epic']}; --card:#1b1e25; --line:#2a2e38; --ink:#e7e9ee; --dim:#878e9c;
  background:#14161b; color:var(--ink); font-family:'Outfit',sans-serif; padding:26px 18px 70px; min-height:100vh; box-sizing:border-box;}}
#sw-fc *{{ box-sizing:border-box; }}
.h1{{ font-family:'Saira Condensed'; font-weight:700; letter-spacing:.14em; text-transform:uppercase; font-size:14px; color:#7f8694; margin:0 0 6px;}}
.lead{{ color:#aab0bd; font-size:14px; max-width:820px; line-height:1.5; margin:0 0 24px;}}
.fc{{ max-width:760px; margin:0 auto 34px;}}
.ctitle{{ display:flex; align-items:baseline; gap:10px; margin:0 2px 12px;}}
.ctitle .tag{{ font-family:'Saira Condensed'; font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:12px; color:#8b93a3; background:#23262e; padding:3px 9px; border-radius:6px;}}
.ctitle .nm{{ font-size:16px; color:#dfe3ea; font-weight:600;}}
.ctitle .ds{{ font-size:12.5px; color:var(--dim);}}
.card{{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:15px 16px 17px;}}
.fhead{{ display:flex; align-items:center; gap:10px; margin-bottom:14px;}}
.fhead .ico{{ width:30px; height:30px; color:#cfd4de;}}
.fhead .t{{ font-weight:600; font-size:15px;}}
.fhead .s{{ font-size:12px; color:var(--dim); margin-left:auto;}}
svg.icon{{ width:100%; height:100%; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round;}}
.choose button{{ font-family:'Saira Condensed'; letter-spacing:.08em; text-transform:uppercase; font-size:12px; background:#23262e; color:#cdd2dc; border:1px solid #343843; border-radius:20px; padding:7px 16px; cursor:pointer; margin-top:12px;}}

/* F1 heat ribbon */
.ribbon{{ display:flex; flex-direction:column; gap:4px;}}
.rrow{{ display:flex; align-items:center; gap:8px;}}
.rlab{{ width:46px; flex:0 0 46px; font-size:11px; color:#cfd4de; display:flex; align-items:baseline; gap:5px;}}
.rlab b{{ font-weight:600;}} .rlab span{{ color:var(--dim); font-size:10px;}}
.cells{{ display:flex; gap:3px; flex:1;}}
.hc{{ flex:1; height:22px; border-radius:3px; opacity:.92;}}
.hc.peak{{ outline:2px solid #fff; outline-offset:-1px; opacity:1;}}
.axis .hx{{ flex:1; text-align:center; font-size:9px; color:var(--dim);}}
.axis .rlab, .axis .cells{{ height:14px;}}
.rbest{{ width:26px; text-align:right; font-weight:800; font-size:13px;}}

/* F2 medallion strip */
.mstrip{{ display:flex; gap:10px; justify-content:space-between;}}
.dm{{ text-align:center; flex:1;}}
.dring{{ width:54px; height:54px; border-radius:50%; margin:0 auto 5px; position:relative;
  background:conic-gradient(var(--c) calc(var(--p)*1%), #2a2e38 0);}}
.dring::after{{ content:''; position:absolute; inset:4px; border-radius:50%; background:var(--card);}}
.di{{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; z-index:1;}}
.dd{{ font-size:9.5px; color:var(--dim); text-transform:uppercase; letter-spacing:.04em;}}
.ds{{ font-weight:800; font-size:15px; line-height:1;}}
.dt{{ font-size:10px; color:#aab0bd;}} .dk{{ font-size:9.5px; color:var(--dim);}}

/* F3 columns */
.cols{{ display:flex; gap:9px; align-items:flex-end;}}
.cc{{ flex:1; text-align:center;}}
.cbar{{ height:96px; background:#11141b; border:1px solid var(--line); border-radius:6px; display:flex; align-items:flex-end; overflow:hidden;}}
.cfill{{ width:100%; border-radius:5px 5px 0 0;}}
.cn{{ font-weight:800; font-size:14px; margin-top:5px;}} .cd{{ font-size:11px; color:#cfd4de;}} .ck{{ font-size:9.5px; color:var(--dim);}}
</style>

<svg width="0" height="0" style="position:absolute"><defs>
<symbol id="i-kite" viewBox="0 0 24 24"><path d="M2.5 7 Q12 1 21.5 7"/><path d="M5.5 7.6 L11 15.5"/><path d="M18.5 7.6 L13 15.5"/><path d="M10.5 15.6 H13.5"/><path d="M7 20 Q12 22.5 17 20"/></symbol>
</defs></svg>

<div class="h1">Swelligence · 7-day forecast renderings</div>
<p class="lead">How the next 7 days look when you tap a Heat-Grid cell or a Medallion — shown for
<b>Hurst / Keyhaven · Kitesurf</b>. Two styles echo your chosen cards; a third (columns) for reference.
Real daily bests; hourly synthesised to show the shape.</p>

<div class="fc">
  <div class="ctitle"><span class="tag">F1</span><span class="nm">Heat-ribbon</span><span class="ds">— pairs with Heat-Grid: rows=days, cols=daylight hours, brightest cell = best window</span></div>
  <div class="card">
    <div class="fhead"><div class="ico"><svg class="icon"><use href="#i-kite"/></svg></div><div class="t">Hurst / Keyhaven · Kitesurf</div><div class="s">next 7 days · 06–21h</div></div>
    {ribbon()}
  </div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Heat-ribbon')">Choose Heat-ribbon</button></div>
</div>

<div class="fc">
  <div class="ctitle"><span class="tag">F2</span><span class="nm">Day medallions</span><span class="ds">— pairs with Medallions: 7 mini-rings, each fills to that day's best; time + rig below</span></div>
  <div class="card">
    <div class="fhead"><div class="ico"><svg class="icon"><use href="#i-kite"/></svg></div><div class="t">Hurst / Keyhaven · Kitesurf</div><div class="s">best window per day</div></div>
    {medallions()}
  </div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Day-medallions')">Choose Day medallions</button></div>
</div>

<div class="fc">
  <div class="ctitle"><span class="tag">F3</span><span class="nm">Columns</span><span class="ds">— classic bar chart (reference)</span></div>
  <div class="card">
    <div class="fhead"><div class="ico"><svg class="icon"><use href="#i-kite"/></svg></div><div class="t">Hurst / Keyhaven · Kitesurf</div><div class="s">best window per day</div></div>
    {columns()}
  </div>
  <div class="choose"><button onclick="window.__sp_choose&&window.__sp_choose('Columns')">Choose Columns</button></div>
</div>

</div>
"""

with open(OUT, "w") as f:
    f.write(HTML)
print("wrote", os.path.normpath(OUT), len(HTML), "bytes")
