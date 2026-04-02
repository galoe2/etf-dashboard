"""
ETF Market Intelligence Dashboard — Unified
Sectors (12) + Countries (8 regions) + News in one tabbed interface.
Requirements: pip install numpy pandas yfinance
Optional: news_data.json from run_news.py
Usage: python build_dashboard.py
"""
import math, os, json, sys, re
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

AUTHOR = "Gennaro Aloe"
LEVERAGED = {"TQQQ","SOXL","LABU"}

SECTOR_MAP = {
    "Broad Market":{"SPY":"S&P 500","QQQ":"Nasdaq 100","DIA":"Dow Jones 30","VTI":"Total US Market","IWM":"Russell 2000"},
    "International":{"EEM":"Emerging Markets","EFA":"Developed ex-US","KWEB":"China Internet"},
    "Tech & Semiconductors":{"XLK":"US Tech","VGT":"Info Technology","ARKK":"Disruptive Innovation","BOTZ":"Robotics & AI","SMH":"Semiconductors","HACK":"Cybersecurity","CIBR":"Cyber Defense","SKYY":"Cloud Computing","CLOU":"Cloud Software"},
    "Healthcare":{"XLV":"Healthcare","XBI":"Biotech Small Cap","IBB":"Biotech Large Cap","ARKG":"Genomics"},
    "Financials":{"XLF":"Financial Sector","FINX":"Fintech"},
    "Energy":{"XLE":"Oil & Gas","USO":"Crude Oil","URA":"Uranium","TAN":"Solar","ICLN":"Clean Energy","QCLN":"Clean Tech"},
    "Commodities":{"XLB":"Materials","COPX":"Copper Miners","REMX":"Rare Earth","SLV":"Silver","GLD":"Gold","GDX":"Gold Miners"},
    "Real Estate":{"XLRE":"Real Estate","VNQ":"REITs","ITB":"Homebuilders","XHB":"Housing"},
    "Industrials":{"XLI":"Industrials","JETS":"Airlines","DRIV":"EV & Auto","IDRV":"Self-Driving","ITA":"Aerospace & Defense","UFO":"Space","ARKX":"Space Exploration","PAVE":"Infrastructure"},
    "Bonds":{"TLT":"20Y+ Treasury","HYG":"High Yield","LQD":"Investment Grade"},
    "Crypto":{"BITO":"Bitcoin Futures","BLOK":"Blockchain"},
    "Consumers":{"XLP":"Staples","XLY":"Discretionary","XLC":"Communications","ESPO":"Gaming"},
    "Utilities":{"XLU":"Utilities"},
}
SEC_ORDER = list(SECTOR_MAP.keys())
SEC_TICKER = {}; SEC_DESC = {}
for s, tks in SECTOR_MAP.items():
    for t, d in tks.items(): SEC_TICKER[t] = s; SEC_DESC[t] = d

COUNTRY_MAP = {
    "United States":{"SPY":"S&P 500","QQQ":"Nasdaq 100","DIA":"Dow Jones","IWM":"Russell 2000","VTI":"Total Market"},
    "Europe":{"EZU":"Eurozone","VGK":"FTSE Europe","EWG":"Germany","EWQ":"France","EWI":"Italy","EWP":"Spain","EWU":"UK","EWL":"Switzerland","EWD":"Sweden","EWN":"Netherlands"},
    "China":{"FXI":"Large Cap","KWEB":"Internet","MCHI":"MSCI China","GXC":"S&P China","CQQQ":"Tech","ASHR":"CSI 300","CHIQ":"Consumer"},
    "India":{"INDA":"MSCI India","SMIN":"Small Cap","INDY":"Nifty 50","EPI":"Earnings"},
    "EM Asia":{"EWT":"Taiwan","EWY":"South Korea","EWM":"Malaysia","THD":"Thailand","VNM":"Vietnam","EIDO":"Indonesia","EPHE":"Philippines","EWS":"Singapore"},
    "EM Latin America":{"EWZ":"Brazil","EWW":"Mexico","ECH":"Chile","ARGT":"Argentina","GXG":"Colombia"},
    "EM Africa & Middle East":{"EZA":"South Africa","KSA":"Saudi Arabia","UAE":"UAE","QAT":"Qatar","TUR":"Turkey"},
    "Other":{"EWJ":"Japan","EWA":"Australia","EWC":"Canada","ENZL":"New Zealand","EIS":"Israel"},
}
REG_ORDER = list(COUNTRY_MAP.keys())
REG_TICKER = {}; REG_DESC = {}
for r, tks in COUNTRY_MAP.items():
    for t, d in tks.items(): REG_TICKER[t] = r; REG_DESC[t] = d

ALL_TICKERS = sorted(set(list(SEC_TICKER.keys()) + list(REG_TICKER.keys())))

# News
NEWS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_data.json')
NEWS = None
if os.path.exists(NEWS_PATH):
    try:
        with open(NEWS_PATH, 'r', encoding='utf-8') as f: NEWS = json.load(f)
        print(f"News loaded: {NEWS.get('total_articles',0)} articles")
    except: print("WARN: news_data.json failed to load")

# ═══════════════════════════════════════════
# DATA DOWNLOAD
# ═══════════════════════════════════════════
import yfinance as yf
print(f"\nDownloading {len(ALL_TICKERS)} ETFs...")
end_date = datetime.now()
start_date = end_date - timedelta(days=4*365)
raw = yf.download(ALL_TICKERS, start=start_date.strftime("%Y-%m-%d"),
                  end=end_date.strftime("%Y-%m-%d"), group_by="ticker",
                  auto_adjust=True, progress=False, threads=True)
REPORT_DATE = end_date.strftime("%B %d, %Y")

daily_close = {}; daily_volume = {}; daily_high = {}; daily_low = {}
failed = []
for tk in ALL_TICKERS:
    try:
        d = raw[tk].dropna(subset=["Close"]) if len(ALL_TICKERS) > 1 else raw.dropna(subset=["Close"])
        if len(d) < 30: raise ValueError(f"Only {len(d)} rows")
        daily_close[tk] = d["Close"]; daily_volume[tk] = d["Volume"]
        daily_high[tk] = d["High"]; daily_low[tk] = d["Low"]
    except:
        failed.append(tk)
for tk in failed:
    SEC_TICKER.pop(tk, None); SEC_DESC.pop(tk, None)
    REG_TICKER.pop(tk, None); REG_DESC.pop(tk, None)
    for m in [SECTOR_MAP, COUNTRY_MAP]:
        for s in list(m.keys()):
            if tk in m[s]: del m[s][tk]
ALL_TICKERS = [t for t in ALL_TICKERS if t not in failed]
print(f"  OK: {len(ALL_TICKERS)} tickers, {len(failed)} failed: {failed[:10]}")

# ═══════════════════════════════════════════
# CALCULATIONS
# ═══════════════════════════════════════════
PERF_WINDOWS = {"w1":5,"m1":21,"m3":63,"m6":126,"y1":252,"y3":756}

def calc_perf(closes, w):
    if len(closes) < w+1: return 0.0
    p = closes.iloc[-1]; q = closes.iloc[-(w+1)]
    if q == 0: return 0.0
    return round((p/q-1)*100, 2)

def calc_rsi(closes, period=14):
    if len(closes) < period+5: return 50.0
    d = closes.diff().dropna()
    g = d.clip(lower=0); l = (-d.clip(upper=0))
    ag = g.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    al = l.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    return round(float(v), 1) if np.isfinite(v) else 50.0

def calc_flow(tk):
    if tk not in daily_close or tk not in daily_volume: return None
    v = daily_volume[tk]; c = daily_close[tk]; h = daily_high[tk]; lo = daily_low[tk]
    if len(v) < 25: return None
    vc = float(v.iloc[-5:].mean()); v20 = float(v.iloc[-25:-5].mean()) if len(v)>=25 else vc
    vol_pct = round((vc/v20-1)*100) if v20>0 else 0
    pc = float(c.iloc[-1]/c.iloc[-5]-1) if len(c)>=5 else 0
    if h is not None and lo is not None and len(h)>=5:
        sn = float(((h.iloc[-5:]-lo.iloc[-5:])/c.iloc[-5:]).mean())
        s20 = float(((h.iloc[-25:-5]-lo.iloc[-25:-5])/c.iloc[-25:-5]).mean()) if len(h)>=25 else sn
        sd = round((sn/s20-1)*100) if s20>0 else 0
    else: sd = 0
    direction = 1 if pc > 0 else -1
    sf = -1 if sd > 5 else (1 if sd < -3 else 0)
    fs = int(direction*min(abs(vol_pct),100)*0.7 + sf*15 + pc*200)
    return {"vol_pct":vol_pct,"spread_delta":sd,"flow_score":max(-100,min(100,fs)),
            "vol_current":vc,"vol_20d":v20,"price_chg":round(pc*100,2)}

def fmt_vol(v):
    if v>=1e9: return f"{v/1e9:.1f}B"
    if v>=1e6: return f"{v/1e6:.0f}M"
    return f"{v/1e3:.0f}K"

# Process ETFs for a universe
def process_etfs(ticker_map, desc_map, group_order):
    etfs = []; rsi_data = {}
    for tk in ALL_TICKERS:
        if tk not in ticker_map: continue
        cl = daily_close[tk]
        e = {"ticker":tk,"desc":desc_map.get(tk,""),"group":ticker_map[tk],"is_lev":tk in LEVERAGED}
        for k, d in PERF_WINDOWS.items(): e[k] = calc_perf(cl, d)
        rsi = calc_rsi(cl)
        e["rsi"] = rsi
        if tk not in LEVERAGED: rsi_data[tk] = rsi
        fl = calc_flow(tk)
        e["flow"] = fl if fl else {"vol_pct":0,"spread_delta":0,"flow_score":0,"vol_current":0,"vol_20d":0,"price_chg":0}
        etfs.append(e)
    non_lev = [e for e in etfs if not e["is_lev"]]
    # Group averages
    grp_avgs = {}
    for g in group_order:
        members = [e for e in non_lev if e["group"]==g]
        if not members: continue
        avg = {k: round(sum(e[k] for e in members)/len(members), 2) for k in PERF_WINDOWS}
        avg["rsi"] = round(sum(e["rsi"] for e in members)/len(members), 1)
        avg["count"] = len(members)
        grp_avgs[g] = avg
    return etfs, non_lev, grp_avgs, rsi_data

print("Computing sector data...")
sec_etfs, sec_nl, sec_avgs, sec_rsi = process_etfs(SEC_TICKER, SEC_DESC, SEC_ORDER)
print("Computing country data...")
reg_etfs, reg_nl, reg_avgs, reg_rsi = process_etfs(REG_TICKER, REG_DESC, REG_ORDER)

# ═══════════════════════════════════════════
# RISK METRICS
# ═══════════════════════════════════════════
all_rsi_values = list(sec_rsi.values()) + list(reg_rsi.values())
n_overbought = sum(1 for r in all_rsi_values if r > 70)
n_oversold = sum(1 for r in all_rsi_values if r < 30)
n_total_rsi = len(all_rsi_values) if all_rsi_values else 1
pct_overbought = round(n_overbought / n_total_rsi * 100)
pct_oversold = round(n_oversold / n_total_rsi * 100)

def calc_max_drawdown(closes, days=63):
    if len(closes) < days: return 0.0
    window = closes.iloc[-days:]
    peak = window.expanding().max()
    dd = ((window - peak) / peak)
    return round(float(dd.min()) * 100, 1)

drawdowns = {}
for tk in ALL_TICKERS:
    if tk in daily_close and tk not in LEVERAGED:
        dd = calc_max_drawdown(daily_close[tk])
        if dd < -2: drawdowns[tk] = dd
worst_dd = sorted(drawdowns.items(), key=lambda x: x[1])[:5]

spy_cl = daily_close.get("SPY")
realized_vol = 0.0
if spy_cl is not None and len(spy_cl) > 21:
    ret = spy_cl.pct_change().dropna().iloc[-21:]
    realized_vol = round(float(ret.std() * (252**0.5) * 100), 1)

risk_score = min(100, int(pct_oversold * 2 + max(0, realized_vol - 15) * 3 + (100 - pct_overbought)))
print(f"  Risk: vol={realized_vol}%, OB={pct_overbought}%, OS={pct_oversold}%, score={risk_score}")

# Pre-compute KPI strings
dd_kpi_val = f"{worst_dd[0][1]:+.1f}%" if worst_dd else "—"
dd_kpi_desc = f"{worst_dd[0][0]} {SEC_DESC.get(worst_dd[0][0], REG_DESC.get(worst_dd[0][0],''))}" if worst_dd else ""

# Momentum
def calc_momentum(grp_avgs, group_order, rsi_data, ticker_map):
    groups = [g for g in group_order if g in grp_avgs]
    weights = {"w1":0.30,"m1":0.25,"m3":0.20,"y1":0.15,"y3":0.10}
    raw = {}
    for g in groups:
        score = 0
        for tf, w in weights.items():
            rank = sorted(groups, key=lambda x: grp_avgs[x].get(tf,0)).index(g)
            score += (rank/max(len(groups)-1,1))*w*100
        tks = [tk for tk in ALL_TICKERS if ticker_map.get(tk)==g and tk in rsi_data]
        if tks:
            avg_rsi = sum(rsi_data[tk] for tk in tks)/len(tks)
            score = score*0.75 + avg_rsi*0.25
        raw[g] = score
    mn = min(raw.values()) if raw else 0; mx = max(raw.values()) if raw else 1
    rng = mx-mn if mx>mn else 1
    result = {}
    sorted_mom = sorted(raw.items(), key=lambda x: x[1], reverse=True)
    for rank, (g, v) in enumerate(sorted_mom, 1):
        sc = round((v-mn)/rng*85+10)
        w1 = grp_avgs[g].get("w1",0)
        prev = max(10, min(95, sc + (-w1*2)))
        result[g] = {"score":sc,"prev_rank":rank,"prev_score":int(prev)}
    return result

sec_mom = calc_momentum(sec_avgs, SEC_ORDER, sec_rsi, SEC_TICKER)
reg_mom = calc_momentum(reg_avgs, REG_ORDER, reg_rsi, REG_TICKER)

# Capital flows per group
def calc_group_flows(etfs, ticker_map, group_order, desc_map):
    sector_flows = {}
    for g in group_order:
        members = [e for e in etfs if e["group"]==g and not e["is_lev"]]
        if not members: continue
        flows = [(e["ticker"], e["flow"]) for e in members if e["flow"]["flow_score"] != 0 or e["flow"]["vol_pct"] != 0]
        if not flows: continue
        avg_vp = round(sum(f["vol_pct"] for _,f in flows)/len(flows))
        avg_fs = round(sum(f["flow_score"] for _,f in flows)/len(flows))
        total_vc = sum(f["vol_current"] for _,f in flows)
        total_v20 = sum(f["vol_20d"] for _,f in flows)
        avg_sd = round(sum(f["spread_delta"] for _,f in flows)/len(flows))
        top_vol = sorted(flows, key=lambda x: abs(x[1]["vol_pct"]), reverse=True)[:3]
        tks = [t for t,_ in top_vol]
        details = []
        for t, f in top_vol:
            if f["vol_pct"] > 10: details.append(f"{t} vol +{f['vol_pct']}% vs 20d")
            elif f["vol_pct"] < -10: details.append(f"{t} vol {f['vol_pct']}% vs 20d")
        stxt = f"Spread {'tightening' if avg_sd<-3 else 'widening' if avg_sd>3 else 'stable'} {abs(avg_sd)}%."
        detail = ". ".join(details) + ". " + stxt if details else stxt
        sector_flows[g] = {"tickers":tks,"vol_pct":avg_vp,"flow_score":avg_fs,
            "volume_20d_avg":fmt_vol(total_v20),"volume_current":fmt_vol(total_vc),
            "bid_ask_delta":f"{avg_sd:+d}%","detail":detail}
    inflow = sorted([{"group":g,**v} for g,v in sector_flows.items() if v["flow_score"]>15],key=lambda x:x["flow_score"],reverse=True)[:4]
    outflow = sorted([{"group":g,**v} for g,v in sector_flows.items() if v["flow_score"]<-15],key=lambda x:x["flow_score"])[:4]
    return {"inflow":inflow,"outflow":outflow}

sec_flows = calc_group_flows(sec_etfs, SEC_TICKER, SEC_ORDER, SEC_DESC)
reg_flows = calc_group_flows(reg_etfs, REG_TICKER, REG_ORDER, REG_DESC)

# Correlations (sector only — too many country pairs)
def sector_weekly_returns(sector, weeks):
    members = [tk for tk in ALL_TICKERS if SEC_TICKER.get(tk)==sector and tk not in LEVERAGED and tk in daily_close]
    if not members: return None
    wrs = []
    for tk in members:
        wk = daily_close[tk].resample("W-FRI").last().dropna()
        wr = wk.pct_change().dropna().iloc[-weeks:]
        if len(wr) >= weeks*0.8: wrs.append(wr)
    if not wrs: return None
    c = pd.concat(wrs, axis=1).dropna()
    return c.mean(axis=1) if len(c)>10 else None

CORRELATIONS = []
slist = [s for s in SEC_ORDER if s in sec_avgs]
for i, sa in enumerate(slist):
    for sb in slist[i+1:]:
        ra = sector_weekly_returns(sa, 156); rb = sector_weekly_returns(sb, 156)
        if ra is not None and rb is not None:
            c = pd.concat([ra,rb],axis=1).dropna()
            c3y = round(float(c.iloc[:,0].corr(c.iloc[:,1])),2) if len(c)>12 else 0
        else: c3y = 0
        ra2 = sector_weekly_returns(sa, 13); rb2 = sector_weekly_returns(sb, 13)
        if ra2 is not None and rb2 is not None:
            c2 = pd.concat([ra2,rb2],axis=1).dropna()
            c3m = round(float(c2.iloc[:,0].corr(c2.iloc[:,1])),2) if len(c2)>8 else 0
        else: c3m = 0
        CORRELATIONS.append((sa,sb,c3y,c3m))
print(f"  Correlations: {len(CORRELATIONS)} pairs")

# Chart data (sector + country)
chart_prices_sec = {}; chart_prices_reg = {}
for tk in ALL_TICKERS:
    if tk in LEVERAGED: continue
    cl = daily_close[tk]
    wk = cl.resample("W-FRI").last().dropna()
    if len(wk)<2: continue
    norm = wk.values[-1]
    prices = [round(float(p/norm*100),2) for p in wk.values]
    if tk in SEC_TICKER: chart_prices_sec[tk] = prices
    if tk in REG_TICKER: chart_prices_reg[tk] = prices

sector_prices = {}
for s in SEC_ORDER:
    members = [tk for tk in ALL_TICKERS if SEC_TICKER.get(tk)==s and tk not in LEVERAGED and tk in chart_prices_sec]
    if not members: continue
    ml = min(len(chart_prices_sec[t]) for t in members)
    sector_prices[s] = [round(sum(chart_prices_sec[t][i] for t in members)/len(members),2) for i in range(ml)]

region_prices = {}
for r in REG_ORDER:
    members = [tk for tk in ALL_TICKERS if REG_TICKER.get(tk)==r and tk not in LEVERAGED and tk in chart_prices_reg]
    if not members: continue
    ml = min(len(chart_prices_reg[t]) for t in members)
    region_prices[r] = [round(sum(chart_prices_reg[t][i] for t in members)/len(members),2) for i in range(ml)]

# Lagged cross-correlation
def weekly_returns(prices):
    p = np.array(prices,dtype=float)
    return np.diff(p)/p[:-1]

def lagged_xcorr(ap,bp,max_lag=26):
    ra = weekly_returns(ap); rb = weekly_returns(bp)
    n = min(len(ra),len(rb)); ra=ra[-n:]; rb=rb[-n:]
    window = min(52,n-max_lag-1)
    if window<20: return 0,0,{}
    results = {}
    for lag in range(-max_lag,max_lag+1):
        if lag>=0: a_s=ra[max_lag:max_lag+window]; b_s=rb[max_lag+lag:max_lag+lag+window]
        else: a_s=ra[max_lag-lag:max_lag-lag+window]; b_s=rb[max_lag:max_lag+window]
        if len(a_s)!=window or len(b_s)!=window: continue
        if np.std(a_s)<1e-10 or np.std(b_s)<1e-10: continue
        c = np.corrcoef(a_s,b_s)[0,1]
        if np.isfinite(c): results[lag]=round(float(c),3)
    if not results: return 0,0,{}
    bl = max(results,key=lambda k:abs(results[k]))
    return bl,results[bl],results

lag_analysis = {}
for sa,sb,c3y,c3m in CORRELATIONS:
    key = tuple(sorted([sa,sb]))
    kstr = f"{key[0]}|{key[1]}"
    if kstr in lag_analysis: continue
    if sa not in sector_prices or sb not in sector_prices: continue
    bl,bc,all_lags = lagged_xcorr(sector_prices[sa],sector_prices[sb])
    c0 = all_lags.get(0,0)
    if abs(bl)>=3 and abs(bc)>abs(c0)+0.05:
        ldr = sa if bl>0 else sb; flw = sb if bl>0 else sa
        lag_analysis[kstr] = {"leader":ldr,"follower":flw,"lag_weeks":abs(bl),"lag_corr":abs(bc),"concurrent_corr":c0,"improvement":round(abs(bc)-abs(c0),3)}
    else:
        lag_analysis[kstr] = {"leader":None,"follower":None,"lag_weeks":0,"lag_corr":abs(c0),"concurrent_corr":c0,"improvement":0}

# Chart JSON
max_weeks_sec = min(len(v) for v in chart_prices_sec.values()) if chart_prices_sec else 0
max_weeks_reg = min(len(v) for v in chart_prices_reg.values()) if chart_prices_reg else 0
_ref = "SPY" if "SPY" in daily_close else list(daily_close.keys())[0]
_ref_wk = daily_close[_ref].resample("W-FRI").last().dropna()
all_dates = [d.strftime("%Y-%m-%d") for d in _ref_wk.index[-max(max_weeks_sec,max_weeks_reg):]]

chart_sec = {"tickers":{},"sectors":{},"startDate":all_dates[0] if all_dates else "","numWeeks":max_weeks_sec,"corr":{}}
for tk,prices in chart_prices_sec.items():
    e = next((x for x in sec_nl if x["ticker"]==tk),None)
    if not e: continue
    chart_sec["tickers"][tk] = {"d":e["desc"],"s":e["group"],"p":[round(x,1) for x in prices[:max_weeks_sec]]}
for s,prices in sector_prices.items():
    chart_sec["sectors"][s] = [round(x,1) for x in prices[:max_weeks_sec]]
seen = set()
for sa,sb,c3y,c3m in CORRELATIONS:
    key = tuple(sorted([sa,sb]))
    if key in seen: continue; seen.add(key)
    kstr = f"{key[0]}|{key[1]}"; la = lag_analysis.get(kstr,{})
    chart_sec["corr"][kstr] = {"y3":c3y,"m3":c3m,"leader":la.get("leader"),"follower":la.get("follower"),"lag_w":la.get("lag_weeks",0),"lag_r":la.get("lag_corr",0)}

chart_reg = {"tickers":{},"regions":{},"startDate":all_dates[0] if all_dates else "","numWeeks":max_weeks_reg}
for tk,prices in chart_prices_reg.items():
    e = next((x for x in reg_nl if x["ticker"]==tk),None)
    if not e: continue
    chart_reg["tickers"][tk] = {"d":e["desc"],"s":e["group"],"p":[round(x,1) for x in prices[:max_weeks_reg]]}
for r,prices in region_prices.items():
    chart_reg["regions"][r] = [round(x,1) for x in prices[:max_weeks_reg]]

# Correlation AI commentary
corr_comments = {}
for sa,sb,c3y,c3m in CORRELATIONS:
    key = tuple(sorted([sa,sb])); kstr = f"{key[0]}|{key[1]}"
    if kstr in corr_comments: continue
    delta = c3m - c3y
    la = lag_analysis.get(kstr,{})
    lag_text = ""
    if la.get("leader"):
        ldr=la["leader"];flw=la["follower"];lw=la["lag_weeks"];lr=la["lag_corr"];cc=la["concurrent_corr"]
        lag_text = f' <strong>Lead/lag:</strong> {ldr} leads {flw} by ~{lw}w (r={lr:.2f} vs concurrent {cc:.2f}).'
    if delta>0.15: comment = f"Rapid convergence ({delta:+.2f}). Synchronized movement risk."
    elif delta>0.05: comment = f"Moderate convergence ({delta:+.2f}). Shared catalysts."
    elif delta<-0.15: comment = f"Significant divergence ({delta:+.2f}). Regime shift."
    elif delta<-0.05: comment = f"Mild divergence ({delta:+.2f}). Decoupling from historical."
    else: comment = f"Stable ({delta:+.2f}). Correlation {c3y:.2f} holding."
    if lag_text: comment += lag_text
    corr_comments[kstr] = comment

# ═══════════════════════════════════════════
# AGGREGATE DATA
# ═══════════════════════════════════════════
spy = next(e for e in sec_etfs if e["ticker"]=="SPY")
qqq = next(e for e in sec_etfs if e["ticker"]=="QQQ")
be = max(sec_nl, key=lambda x:x["w1"])
we = min(sec_nl, key=lambda x:x["w1"])
bs = max(sec_avgs.items(), key=lambda x:x[1]["w1"])
ws = min(sec_avgs.items(), key=lambda x:x[1]["w1"])
ps = sum(1 for v in sec_avgs.values() if v["w1"]>0)
top_g = sorted(sec_nl, key=lambda x:x["w1"], reverse=True)[:5]
top_l = sorted(sec_nl, key=lambda x:x["w1"])[:5]
rsi_sorted = sorted(sec_rsi.items(), key=lambda x:x[1])
rsi_lo5 = rsi_sorted[:5]; rsi_hi5 = rsi_sorted[-5:][::-1]

# Country top/bottom
br = max(reg_avgs.items(), key=lambda x:x[1]["w1"])
wr = min(reg_avgs.items(), key=lambda x:x[1]["w1"])
top_reg = sorted(reg_nl, key=lambda x:x["w1"], reverse=True)[:5]
bot_reg = sorted(reg_nl, key=lambda x:x["w1"])[:5]

# Analysis JSON for AI — includes news for full context
news_summary = {}
if NEWS and NEWS.get('sector_news'):
    for sec, d in NEWS['sector_news'].items():
        tops = []
        for a in d.get('top', [])[:2]:
            tops.append({"hl": a.get('headline','')[:100], "impact": a.get('impact','neutral'), "src": a.get('source','')})
        news_summary[sec] = {"count": d["count"], "top": tops}
    for a in NEWS.get('articles', [])[:8]:
        pass  # sector_news already covers this

news_rotations = []
if NEWS and NEWS.get('rotation_signals'):
    news_rotations = [{"signal": r["signal"][:120], "source": r["source"]} for r in NEWS['rotation_signals'][:5]]

analysis_data = {
    "report_date":REPORT_DATE,
    "market_overview":{"spy_1w":spy["w1"],"qqq_1w":qqq["w1"],"breadth":f"{ps}/{len(sec_avgs)}",
        "best_sector":{"name":bs[0],"w1":round(bs[1]["w1"],2)},"worst_sector":{"name":ws[0],"w1":round(ws[1]["w1"],2)},
        "best_etf":{"ticker":be["ticker"],"desc":be["desc"],"w1":be["w1"]},"worst_etf":{"ticker":we["ticker"],"desc":we["desc"],"w1":we["w1"]}},
    "sector_performance":{s:{k:round(v[k],2) for k in ["w1","m1","m3","m6","y1","y3"]} for s,v in sec_avgs.items()},
    "country_performance":{r:{k:round(v[k],2) for k in ["w1","m1","m3","m6","y1","y3"]} for r,v in reg_avgs.items()},
    "top_gainers":[{"t":e["ticker"],"d":e["desc"],"w1":e["w1"]} for e in top_g],
    "top_losers":[{"t":e["ticker"],"d":e["desc"],"w1":e["w1"]} for e in top_l],
    "momentum":{s:{"score":d["score"]} for s,d in sec_mom.items()},
    "country_momentum":{r:{"score":d["score"]} for r,d in reg_mom.items()},
    "capital_flows":{"inflow":[{"group":f["group"],"flow_score":f["flow_score"]} for f in sec_flows["inflow"][:3]],
                     "outflow":[{"group":f["group"],"flow_score":f["flow_score"]} for f in sec_flows["outflow"][:3]]},
    "country_flows":{"inflow":[{"group":f["group"],"flow_score":f["flow_score"]} for f in reg_flows["inflow"][:3]],
                     "outflow":[{"group":f["group"],"flow_score":f["flow_score"]} for f in reg_flows["outflow"][:3]]},
    "rsi_extremes":{"overbought":[{"t":t,"rsi":r} for t,r in rsi_hi5[:3]],"oversold":[{"t":t,"rsi":r} for t,r in rsi_lo5[:3]]},
    "news_by_sector": news_summary,
    "rotation_signals": news_rotations,
    "best_region":{"name":br[0],"w1":round(br[1]["w1"],2)},
    "worst_region":{"name":wr[0],"w1":round(wr[1]["w1"],2)},
    "top_country_etfs":[{"t":e["ticker"],"d":e["desc"],"w1":e["w1"]} for e in top_reg[:3]],
    "bot_country_etfs":[{"t":e["ticker"],"d":e["desc"],"w1":e["w1"]} for e in bot_reg[:3]],
    "risk":{"realized_vol":realized_vol,"pct_overbought":pct_overbought,"pct_oversold":pct_oversold,
            "risk_score":risk_score,"worst_drawdowns_3m":[{"t":t,"dd":d} for t,d in worst_dd[:5]]},
}

print("Building HTML...")

# ═══════════════════════════════════════════
# AI COMMENTARY via Groq
# ═══════════════════════════════════════════
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ai_commentary_html = ""
if GROQ_API_KEY:
    try:
        from groq import Groq
        print("  Generating AI commentary via Groq...")
        gclient = Groq(api_key=GROQ_API_KEY)
        ai_prompt = f"""Sei un analista istituzionale senior specializzato in ETF. Analizza TUTTI i dati forniti e produci un report in italiano strutturato in 5 sezioni HTML con tag <h3>:

1. <h3>Regime di Mercato & Breadth</h3> — Risk-on/off/rotazionale, ampiezza, forza relativa SPY/QQQ
2. <h3>Rotazione Settoriale & Geografica</h3> — Quali settori/regioni stanno guadagnando momentum, quali perdono. Segnali dai flussi di capitale.
3. <h3>Movimenti Anticipatori & Correlazioni</h3> — Lead/lag significativi, divergenze anomale tra settori correlati
4. <h3>Impatto News & Catalizzatori</h3> — Come le notizie recenti impattano i settori, segnali di rotazione dalle news
5. <h3>Idee di Investimento</h3> — 3-5 trade ideas concrete basate sui dati:
   - ETF specifici da sovrappesare/sottopesare con ticker
   - Timeframe suggerito (breve/medio termine)
   - Livello di convinzione (alta/media/bassa)
   - Rischi specifici per ogni idea

Usa <p>, <strong>, <ul><li> per strutturare. Usa classi CSS: <span class="sig-up">testo</span> per segnali positivi, <span class="sig-dn">testo</span> per negativi. 400-500 parole. Solo HTML grezzo, nessun markdown, nessun backtick.

DATA:
{json.dumps(analysis_data, ensure_ascii=False)}"""

        resp = gclient.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{"role":"user","content":ai_prompt}],
            temperature=0.3, max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        # Clean markdown fences if present
        raw = re.sub(r'```html?\s*', '', raw)
        raw = raw.replace('```', '').strip()
        ai_commentary_html = raw
        print("  AI commentary: OK")
    except Exception as e:
        print(f"  AI commentary: SKIP ({e})")

# ═══════════════════════════════════════════
# HTML HELPERS
# ═══════════════════════════════════════════
_all_vals = [sec_avgs[s][k] for s in SEC_ORDER if s in sec_avgs for k in ["w1","m1","m3","y1"]]
_all_vals += [e[k] for e in sec_nl for k in ["w1","m1","m3","y1"]]
pmx = max(abs(v) for v in _all_vals) if _all_vals else 1

def hv(val):
    i = min(abs(val)/pmx, 1.0)
    if val > 0: bg=f'rgba(34,139,34,{i*.20})'; tc=f'rgba(20,80,20,{0.6+i*0.4})'
    elif val < 0: bg=f'rgba(180,30,30,{i*.20})'; tc=f'rgba(120,20,20,{0.6+i*0.4})'
    else: bg='transparent'; tc='#888'
    return f'<td class="hv" style="background:{bg};color:{tc}">{val:+.2f}</td>'

# Performance table (sectors)
perf_html = ""
for s in SEC_ORDER:
    members = [e for e in sec_nl if e["group"]==s]
    if not members: continue
    a = sec_avgs[s]; sid = s.replace(" ","_").replace("&","n")
    perf_html += f'<tr class="sh" onclick="tgl(\'{sid}\')"><td class="sn">{s} <span class="sa" id="a_{sid}">+</span></td><td class="sc">{a["count"]}</td>{hv(a["w1"])}{hv(a["m1"])}{hv(a["m3"])}{hv(a["y1"])}</tr>\n'
    for e in sorted(members, key=lambda x:x["w1"], reverse=True):
        rsi = sec_rsi.get(e["ticker"])
        rc = ' rsi-lo' if rsi is not None and rsi<35 else ' rsi-hi' if rsi is not None and rsi>65 else ''
        rv = f'{rsi:.0f}' if rsi is not None else '—'
        perf_html += f'<tr class="er g_{sid}" style="display:none"><td class="tk"><span class="tkr">{e["ticker"]}</span><span class="tkd">{e["desc"]}</span></td><td><span class="rsi-tag{rc}">{rv}</span></td>{hv(e["w1"])}{hv(e["m1"])}{hv(e["m3"])}{hv(e["y1"])}</tr>\n'

# Performance table (countries)
_rv = [reg_avgs[r][k] for r in REG_ORDER if r in reg_avgs for k in ["w1","m1","m3","y1"]]
_rv += [e[k] for e in reg_nl for k in ["w1","m1","m3","y1"]]
rpm = max(abs(v) for v in _rv) if _rv else 1

def hvr(val):
    i = min(abs(val)/rpm, 1.0)
    if val > 0: bg=f'rgba(34,139,34,{i*.20})'; tc=f'rgba(20,80,20,{0.6+i*0.4})'
    elif val < 0: bg=f'rgba(180,30,30,{i*.20})'; tc=f'rgba(120,20,20,{0.6+i*0.4})'
    else: bg='transparent'; tc='#888'
    return f'<td class="hv" style="background:{bg};color:{tc}">{val:+.2f}</td>'

reg_perf_html = ""
for r in REG_ORDER:
    members = [e for e in reg_nl if e["group"]==r]
    if not members: continue
    a = reg_avgs[r]; rid = r.replace(" ","_").replace("&","n")
    reg_perf_html += f'<tr class="sh" onclick="tgl(\'{rid}\')"><td class="sn">{r} <span class="sa" id="a_{rid}">+</span></td><td class="sc">{a["count"]}</td>{hvr(a["w1"])}{hvr(a["m1"])}{hvr(a["m3"])}{hvr(a["y1"])}</tr>\n'
    for e in sorted(members, key=lambda x:x["w1"], reverse=True):
        rsi = reg_rsi.get(e["ticker"])
        rc = ' rsi-lo' if rsi is not None and rsi<35 else ' rsi-hi' if rsi is not None and rsi>65 else ''
        rv = f'{rsi:.0f}' if rsi is not None else '—'
        reg_perf_html += f'<tr class="er g_{rid}" style="display:none"><td class="tk"><span class="tkr">{e["ticker"]}</span><span class="tkd">{e["desc"]}</span></td><td><span class="rsi-tag{rc}">{rv}</span></td>{hvr(e["w1"])}{hvr(e["m1"])}{hvr(e["m3"])}{hvr(e["y1"])}</tr>\n'

# Momentum HTML builder
def build_mom_html(mom_data, grp_avgs, etfs_nl, rsi_data, group_order, prefix="s"):
    sorted_m = sorted(mom_data.items(), key=lambda x:x[1]["score"], reverse=True)
    h = ""
    for rank,(g,d) in enumerate(sorted_m,1):
        rd = d["prev_rank"]-rank; sd = d["score"]-d["prev_score"]
        c = "#1a7a5a" if d["score"]>=65 else "#5a9a5a" if d["score"]>=50 else "#b08030" if d["score"]>=40 else "#a04040"
        ra = f'<span class="ru">+{rd}</span>' if rd>0 else f'<span class="rd">{rd}</span>' if rd<0 else '<span class="rz">0</span>'
        sa = f'<span class="ru">+{sd}</span>' if sd>0 else f'<span class="rd">{sd}</span>' if sd<0 else '<span class="rz">0</span>'
        mid = f'{prefix}m_{g.replace(" ","_").replace("&","n")}'
        h += f'<div class="mr" onclick="tgl(\'{mid}\')" style="cursor:pointer"><span class="mi">#{rank}</span><span class="ma">{ra}</span><span class="ml">{g} <span class="sa" id="a_{mid}">+</span></span><div class="mt"><div class="mb" style="width:{d["score"]}%;background:{c}"></div><div class="mm"></div></div><span class="mv" style="color:{c}">{d["score"]}</span><span class="md">{sa}</span></div>\n'
        members = sorted([e for e in etfs_nl if e["group"]==g], key=lambda x:x["w1"], reverse=True)
        for e in members:
            rsi = rsi_data.get(e["ticker"])
            rs = f'<span class="rsi-tag {"rsi-lo" if rsi is not None and rsi<35 else "rsi-hi" if rsi is not None and rsi>65 else ""}">{rsi:.0f}</span>' if rsi is not None else '<span class="rsi-tag">—</span>'
            wc = "p" if e["w1"]>=0 else "n"
            mc = "p" if e["m1"]>=0 else "n"
            m3c = "p" if e["m3"]>=0 else "n"
            h += f'<div class="mr-tk g_{mid}" style="display:none"><span class="mr-tkr">{e["ticker"]}</span><span class="mr-tkd">{e["desc"]}</span><span class="mr-v {wc}">{e["w1"]:+.2f}%</span><span class="mr-v {mc}">{e["m1"]:+.1f}%</span><span class="mr-v {m3c}">{e["m3"]:+.1f}%</span><span class="mr-rsi">{rs}</span></div>\n'
    return h

sec_mom_html = build_mom_html(sec_mom, sec_avgs, sec_nl, sec_rsi, SEC_ORDER, "s")
reg_mom_html = build_mom_html(reg_mom, reg_avgs, reg_nl, reg_rsi, REG_ORDER, "r")

# Pulse
def pulse_row(ticker, desc, val, fmt):
    c = "var(--p)" if val>=50 and fmt=="rsi" else "var(--n)" if val<50 and fmt=="rsi" else "var(--p)" if val>=0 else "var(--n)"
    if fmt=="return": bar_w=min(abs(val)/10*100,100); vs=f'{val:+.2f}%'
    else: bar_w=val; vs=f'{val:.0f}'; c="#8b1a1a" if val<35 else "#1a6b4a" if val>65 else "#666"
    return f'<div class="pl"><span class="pl-tk">{ticker}</span><span class="pl-desc">{desc}</span><div class="pl-bar-w"><div class="pl-bar" style="width:{bar_w:.0f}%;background:{c}"></div></div><span class="pl-val" style="color:{c}">{vs}</span></div>\n'

pulse_g = "".join(pulse_row(e["ticker"],e["desc"],e["w1"],"return") for e in top_g)
pulse_l = "".join(pulse_row(e["ticker"],e["desc"],e["w1"],"return") for e in top_l)
pulse_rhi = "".join(pulse_row(t,SEC_DESC.get(t,""),r,"rsi") for t,r in rsi_hi5)
pulse_rlo = "".join(pulse_row(t,SEC_DESC.get(t,""),r,"rsi") for t,r in rsi_lo5)

# Capital flows
def flow_card(f, direction):
    cls = "fi" if direction=="in" else "fo"
    tks = ", ".join(f["tickers"])
    vc = f"{f['vol_pct']:+d}%" if f["vol_pct"]!=0 else "flat"
    clr = "p" if direction=="in" else "n"
    return f'<div class="fc {cls}"><div class="fh"><span class="fs">{f["group"]}</span><span class="ft">{tks}</span><span class="fscore {"fsp" if direction=="in" else "fsn"}">{f["flow_score"]:+d}</span></div><div class="fm"><div class="fmi"><span class="fml">Vol vs 20d</span><span class="fmv {clr}">{vc}</span></div><div class="fmi"><span class="fml">Spread Δ</span><span class="fmv {clr}">{f["bid_ask_delta"]}</span></div><div class="fmi"><span class="fml">Avg Vol</span><span class="fmv">{f["volume_20d_avg"]}</span></div><div class="fmi"><span class="fml">Cur Vol</span><span class="fmv">{f["volume_current"]}</span></div></div><div class="fd">{f["detail"]}</div></div>\n'

sfi = "".join(flow_card(f,"in") for f in sec_flows["inflow"][:3])
sfo = "".join(flow_card(f,"out") for f in sec_flows["outflow"][:3])
rfi = "".join(flow_card(f,"in") for f in reg_flows["inflow"][:3])
rfo = "".join(flow_card(f,"out") for f in reg_flows["outflow"][:3])

# Tree selectors
def build_tree(group_map, group_order, ticker_map, prefix=""):
    h = ""
    for g in group_order:
        members = [(tk,d) for tk,d in sorted(group_map[g].items()) if tk not in LEVERAGED and tk in daily_close]
        if not members: continue
        gid = prefix+g.replace(" ","_").replace("&","n")
        tks = "".join(f'<label class="tr-tk"><input type="checkbox" value="{tk}" onchange="upd{prefix}()">{tk} <span class="tr-d">{d}</span></label>' for tk,d in members)
        h += f'<div class="tr-sec"><div class="tr-sh" onclick="togSec(\'{gid}\',event)"><span class="tr-arrow" id="ta_{gid}">&#9654;</span><input type="checkbox" value="S:{g}" onchange="secCb{prefix}(this,\'{gid}\')" onclick="event.stopPropagation()" checked>{g} <span class="tr-cnt">{len(members)}</span></div><div class="tr-kids" id="tk_{gid}" style="display:none">{tks}</div></div>\n'
    return h

tree_sec = build_tree(SECTOR_MAP, SEC_ORDER, SEC_TICKER, "")
tree_reg = build_tree(COUNTRY_MAP, REG_ORDER, REG_TICKER, "C")

# News HTML
def build_news_html():
    if not NEWS or not NEWS.get('sector_news'): return '<div style="padding:40px;text-align:center;color:#999">No news data available. Run <code>run_news.py</code> first.</div>'
    icls = {'bullish':'nw-bull','bearish':'nw-bear','mixed':'nw-mix','neutral':''}
    ilbl = {'bullish':('\u25b2 Bullish','nw-imp-b'),'bearish':('\u25bc Bearish','nw-imp-r'),'mixed':('\u25c6 Mixed','nw-imp-m'),'neutral':('\u25cb Neutral','nw-imp-n')}
    sn = NEWS['sector_news']; rots = NEWS.get('rotation_signals',[])
    active = [s for s in SEC_ORDER if s in sn]
    mid = (len(active)+1)//2; c1=active[:mid]; c2=active[mid:]
    used_links = set()
    def rsec(sec):
        nonlocal used_links
        d = sn[sec]
        h = f'<div class="nw-sec"><div class="nw-sec-hd"><span>{sec}</span><span class="nw-sec-cnt">{d["count"]}</span></div>'
        for art in d.get('top',[])[:3]:
            if art.get('link','#') in used_links: continue
            used_links.add(art.get('link','#'))
            imp = art.get('impact','neutral')
            cc = icls.get(imp,''); it,ist = ilbl.get(imp,('\u25cb','nw-imp-n'))
            hl = art.get('headline',''); sm = art.get('summary','')
            src = art.get('source',''); lk = art.get('link','#'); etfs = art.get('etf_tickers',[])
            h += f'<div class="nw-card {cc}"><div class="nw-head"><div class="nw-hl"><a href="{lk}" target="_blank">{hl}</a></div><span class="nw-imp {ist}">{it}</span></div>'
            if sm: h += f'<div class="nw-sum">{sm}</div>'
            h += f'<div class="nw-meta"><span class="nw-src">{src}</span>'
            for etf in etfs[:3]: h += f' <span class="nw-etf">{etf}</span>'
            h += '</div></div>\n'
        return h + '</div>'
    rot_h = ''
    for r in rots[:3]:
        rot_h += f'<div class="nw-rot"><span class="nw-rot-icon">\u21bb</span>{r["signal"]} <span class="nw-src">\u2014 {r["source"]}</span></div>\n'
    gt = NEWS.get('generated','')[:16].replace('T',' ')
    tot = NEWS.get('total_articles',0)
    return f'<div class="nw-info">{tot} articles from top-tier sources. Last scan: {gt}</div>\n{rot_h}\n<div class="nw-grid"><div>{"".join(rsec(s) for s in c1)}</div><div>{"".join(rsec(s) for s in c2)}</div></div>'

news_html = build_news_html()

# AI Commentary - data-driven fallback (no hardcoded numbers)
spy_w = spy["w1"]; qqq_w = qqq["w1"]
regime = "risk-on" if spy_w>0.5 and qqq_w>0.5 else "risk-off" if spy_w<-0.5 and qqq_w<-0.5 else "rotational"

# Build fallback from live data only
fb_parts = []
fb_parts.append(f'<h3>Regime: {regime.upper()}</h3>')
fb_parts.append(f'<p>SPY {spy_w:+.2f}% | QQQ {qqq_w:+.2f}% | Breadth {ps}/{len(sec_avgs)} | Vol realizzata {realized_vol:.1f}%</p>')
fb_parts.append(f'<h3>Top/Bottom settori (1W)</h3>')
fb_parts.append(f'<p><span class="sig-up">{bs[0]}</span> {bs[1]["w1"]:+.2f}% &nbsp; <span class="sig-dn">{ws[0]}</span> {ws[1]["w1"]:+.2f}%</p>')
if worst_dd:
    dd_txt = ", ".join(f'{t} {d:+.1f}%' for t,d in worst_dd[:3])
    fb_parts.append(f'<h3>Drawdown 3M peggiori</h3><p>{dd_txt}</p>')
fb_parts.append(f'<h3>Risk</h3><p>Overbought: {pct_overbought}% degli ETF | Oversold: {pct_oversold}% | Risk score: {risk_score}/100</p>')
fb_parts.append(f'<p style="color:#999;font-size:.85em;margin-top:12px">AI commentary non disponibile — dati in tempo reale sopra.</p>')
narrative = "\n".join(fb_parts)

print("Generating HTML template...")

# ═══════════════════════════════════════════
# TRACK RECORD — save ideas & compare previous
# ═══════════════════════════════════════════
TRACK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
os.makedirs(TRACK_PATH, exist_ok=True)
TRACK_FILE = os.path.join(TRACK_PATH, 'track_record.json')

# Load previous track record
prev_track = {}
if os.path.exists(TRACK_FILE):
    try:
        with open(TRACK_FILE, 'r', encoding='utf-8') as f:
            prev_track = json.load(f)
    except: pass

# Build "previous calls" comparison
track_html = ""
if prev_track and prev_track.get("ideas"):
    prev_date = prev_track.get("date", "?")
    track_html = f'<div class="sec"><div class="card"><h3>Track Record — Report {prev_date}</h3><div class="sd">Risultato delle idee della settimana precedente</div>'
    track_html += '<div style="overflow-x:auto"><table><thead><tr><th style="text-align:left">Ticker</th><th>Idea</th><th>Prezzo allora</th><th>Prezzo ora</th><th>P&L</th></tr></thead><tbody>'
    hits = 0; total_ideas = 0
    for idea in prev_track["ideas"]:
        tk = idea.get("ticker","")
        direction = idea.get("direction","long")  # long or short
        prev_price = idea.get("price", 0)
        if tk in daily_close and prev_price > 0:
            cur_price = float(daily_close[tk].iloc[-1])
            pnl = round((cur_price / prev_price - 1) * 100, 2)
            if direction == "short": pnl = -pnl
            is_hit = pnl > 0
            if is_hit: hits += 1
            total_ideas += 1
            c = "p" if pnl > 0 else "n"
            track_html += f'<tr><td style="text-align:left"><strong>{tk}</strong></td><td>{direction.upper()}</td><td>${prev_price:.2f}</td><td>${cur_price:.2f}</td><td class="hv" style="color:var(--{c});font-weight:600">{pnl:+.2f}%</td></tr>'
    track_html += '</tbody></table></div>'
    if total_ideas > 0:
        rate = round(hits / total_ideas * 100)
        track_html += f'<div style="margin-top:8px;font-size:.84em;color:#666">Hit rate: <strong>{hits}/{total_ideas}</strong> ({rate}%)</div>'
    track_html += '</div></div>'
    print(f"  Track record: {total_ideas} previous ideas loaded")

# Save current week's prices for tickers mentioned in AI commentary
current_ideas = []
# Parse ETF tickers from AI commentary
if ai_commentary_html:
    import re as _re
    mentioned_tks = set(_re.findall(r'\b([A-Z]{2,5})\b', ai_commentary_html))
    for tk in mentioned_tks:
        if tk in daily_close and tk in SEC_DESC:
            current_ideas.append({
                "ticker": tk,
                "price": round(float(daily_close[tk].iloc[-1]), 2),
                "direction": "long",  # default, AI doesn't specify
                "desc": SEC_DESC.get(tk, REG_DESC.get(tk, "")),
            })

# Save track record
new_track = {
    "date": REPORT_DATE,
    "week": datetime.now().strftime("%Y-W%V"),
    "ideas": current_ideas[:10],  # max 10
}
try:
    with open(TRACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_track, f, ensure_ascii=False, indent=2)
    if current_ideas:
        print(f"  Track record: saved {len(current_ideas[:10])} tickers for next week comparison")
except: pass

# ═══════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════
chart_sec_json = json.dumps(chart_sec)
chart_reg_json = json.dumps(chart_reg)
corr_comments_json = json.dumps(corr_comments)

html = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>ETF Market Intelligence Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--p:#1a6b4a;--n:#8b1a1a;--z:#888;--tx:#111;--tx2:#555;--bg:#f5f5f0;--card:#fff;--brd:#ddd;--brd2:#eee;--acc:#1a1a2e;--sidebar:#151520;--sidebar-tx:#bbb;--sidebar-active:#fff;--tab-accent:#e84855}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'IBM Plex Sans',sans-serif;color:var(--tx);background:var(--bg);font-size:13.5px;line-height:1.55;display:flex;min-height:100vh}}
/* SIDEBAR */
.sidebar{{width:220px;background:var(--sidebar);color:var(--sidebar-tx);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100;border-right:1px solid rgba(255,255,255,.06)}}
.sb-logo{{padding:20px 18px 16px;border-bottom:1px solid rgba(255,255,255,.06)}}
.sb-logo h1{{font-size:.92em;font-weight:600;color:#fff;letter-spacing:-.3px;line-height:1.2}}.sb-logo .sub{{font-family:'IBM Plex Mono',monospace;font-size:.62em;color:#666;margin-top:4px;letter-spacing:.5px;text-transform:uppercase}}
.sb-nav{{flex:1;padding:12px 0;overflow-y:auto}}
.sb-item{{display:flex;align-items:center;gap:10px;padding:10px 18px;cursor:pointer;color:var(--sidebar-tx);font-size:.88em;font-weight:400;transition:all .15s;border-left:3px solid transparent;letter-spacing:.2px}}
.sb-item:hover{{color:#fff;background:rgba(255,255,255,.04)}}.sb-item.active{{color:var(--sidebar-active);background:rgba(255,255,255,.06);border-left-color:var(--tab-accent);font-weight:500}}
.sb-icon{{font-size:1.1em;width:20px;text-align:center}}
.sb-meta{{padding:14px 18px;border-top:1px solid rgba(255,255,255,.06);font-family:'IBM Plex Mono',monospace;font-size:.62em;color:#555;line-height:1.7}}
/* MAIN */
.main{{margin-left:220px;flex:1;padding:0;min-width:0}}
.tab-content{{display:none;padding:24px 28px 40px}}.tab-content.active{{display:block}}
.hd{{padding:20px 28px 14px;border-bottom:1px solid var(--brd);background:#fff}}
.hd-row{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px}}
.hd h2{{font-size:1.4em;font-weight:600;letter-spacing:-.3px;color:var(--acc)}}.hd .sub2{{font-size:.82em;color:var(--tx2);margin-top:2px}}
.hd-date{{font-family:'IBM Plex Mono',monospace;font-size:.72em;color:#999;text-align:right}}
/* COMMON */
.sec{{margin-bottom:24px}}.card{{background:var(--card);border:1px solid var(--brd);padding:18px 20px;border-radius:3px}}
.card h3{{font-size:1em;font-weight:600;margin-bottom:2px;color:var(--acc)}}.card .sd{{font-size:.82em;color:var(--tx2);margin-bottom:12px}}
.krow{{display:flex;gap:0;border:1px solid var(--brd);border-radius:3px;margin-bottom:20px;overflow:hidden;background:#fff}}
.ki{{flex:1;padding:12px 14px;border-right:1px solid var(--brd);text-align:center}}.ki:last-child{{border-right:none}}
.ki .kl{{font-family:'IBM Plex Mono',monospace;font-size:.64em;text-transform:uppercase;letter-spacing:1.5px;color:#999;margin-bottom:3px}}
.ki .kv{{font-family:'IBM Plex Mono',monospace;font-size:1.3em;font-weight:600}}.ki .kd{{font-size:.72em;color:var(--tx2);margin-top:2px}}
.p{{color:var(--p);font-weight:500}}.n{{color:var(--n);font-weight:500}}.z{{color:var(--z)}}
.narr{{border:1px solid var(--brd);border-left:3px solid var(--tab-accent);padding:16px 20px;margin-bottom:24px;font-size:.9em;line-height:1.65;background:#fff;border-radius:3px}}
.narr .nl{{font-family:'IBM Plex Mono',monospace;font-size:.68em;text-transform:uppercase;letter-spacing:2px;color:#999;margin-bottom:8px}}
.narr-ai h3{{font-family:'IBM Plex Mono',monospace;font-size:.82em;text-transform:uppercase;letter-spacing:1.2px;color:var(--tab-accent);margin:14px 0 6px;padding-top:10px;border-top:1px solid var(--brd2)}}.narr-ai h3:first-child{{margin-top:0;padding-top:0;border-top:none}}
.narr-ai p{{margin:0 0 8px;color:#222}}.narr-ai strong{{color:var(--acc)}}
.narr-ai ul{{margin:4px 0 10px 16px;padding:0}}.narr-ai li{{margin-bottom:4px;line-height:1.55;color:#333}}
.sig-up{{color:var(--p);font-weight:600}}.sig-dn{{color:var(--n);font-weight:600}}.sig-nt{{color:#b08030;font-weight:600}}
/* TABLE */
table{{width:100%;border-collapse:collapse;font-size:.84em}}
th{{font-family:'IBM Plex Mono',monospace;padding:6px 8px;text-align:right;font-weight:500;font-size:.72em;text-transform:uppercase;letter-spacing:.8px;color:#999;border-bottom:2px solid #333}}
th:first-child{{text-align:left}}td{{padding:5px 8px;text-align:right;border-bottom:1px solid var(--brd2);font-family:'IBM Plex Mono',monospace;font-size:.92em}}
td:first-child{{text-align:left;font-family:'IBM Plex Sans',sans-serif}}
.hv{{font-weight:600;border-left:1px solid rgba(255,255,255,.6)}}
.sh{{cursor:pointer;background:#f8f8f8}}.sh:hover{{background:#f0f0f0}}.sh td{{font-weight:600;padding:8px;border-bottom:1px solid var(--brd)}}
.sn{{font-size:.92em}}.sa{{font-family:'IBM Plex Mono',monospace;font-size:.7em;color:#999;margin-left:6px}}.sc{{font-size:.78em!important;color:#999!important;font-weight:400!important}}
.er td{{font-size:.84em;border-bottom:1px solid #f3f3f3}}.tk{{display:flex;align-items:baseline;gap:6px;text-align:left!important}}
.tkr{{font-family:'IBM Plex Mono',monospace;font-weight:600;color:var(--acc);min-width:42px;font-size:.9em}}.tkd{{font-size:.78em;color:#999;font-weight:400}}
.rsi-tag{{font-family:'IBM Plex Mono',monospace;font-size:.82em;padding:1px 6px;border-radius:2px}}.rsi-lo{{background:#fee;color:var(--n)}}.rsi-hi{{background:#efe;color:var(--p)}}
/* MOMENTUM */
.mr{{display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid var(--brd2)}}.mr:last-child{{border-bottom:none}}
.mi{{font-family:'IBM Plex Mono',monospace;font-size:.82em;width:24px;color:#999;text-align:right;flex-shrink:0}}
.ma{{width:28px;font-family:'IBM Plex Mono',monospace;font-size:.75em;flex-shrink:0;text-align:center}}
.ml{{width:170px;font-size:.88em;font-weight:500;flex-shrink:0}}.mt{{flex:1;height:18px;background:#eee;position:relative;border-radius:1px;overflow:hidden}}
.mb{{height:100%;border-radius:1px}}.mm{{position:absolute;left:50%;top:0;height:100%;border-left:1px dashed #aaa}}
.mv{{width:28px;text-align:right;font-family:'IBM Plex Mono',monospace;font-size:.88em;font-weight:600;flex-shrink:0}}
.md{{width:32px;text-align:right;font-family:'IBM Plex Mono',monospace;font-size:.78em;flex-shrink:0}}
.mr-tk{{display:flex;align-items:center;gap:8px;padding:4px 8px 4px 56px;border-bottom:1px solid #f3f3f3;font-size:.84em;background:#fcfcfc}}
.mr-tkr{{font-family:'IBM Plex Mono',monospace;font-weight:600;color:var(--acc);width:42px;flex-shrink:0;font-size:.9em}}
.mr-tkd{{font-size:.78em;color:#999;width:130px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.mr-v{{font-family:'IBM Plex Mono',monospace;font-size:.88em;width:58px;text-align:right;flex-shrink:0}}
.mr-rsi{{flex-shrink:0;width:32px;text-align:center}}.ru{{color:var(--p);font-weight:600}}.rd{{color:var(--n);font-weight:600}}.rz{{color:#999}}
/* PULSE */
.pulse-grid{{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--brd);border-radius:3px;overflow:hidden}}
.pulse-col{{border-right:1px solid var(--brd);border-bottom:1px solid var(--brd)}}.pulse-col:nth-child(2n){{border-right:none}}.pulse-col:nth-last-child(-n+2){{border-bottom:none}}
.pulse-hd{{font-family:'IBM Plex Mono',monospace;font-size:.7em;text-transform:uppercase;letter-spacing:1.2px;padding:8px 12px;font-weight:500}}
.pulse-hd-gn{{background:#f4faf4;color:var(--p);border-bottom:2px solid var(--p)}}.pulse-hd-ls{{background:#faf4f4;color:var(--n);border-bottom:2px solid var(--n)}}
.pulse-hd-hi{{background:#f4faf4;color:var(--p);border-bottom:2px solid var(--p)}}.pulse-hd-lo{{background:#faf4f4;color:var(--n);border-bottom:2px solid var(--n)}}
.pl{{display:flex;align-items:center;gap:6px;padding:7px 12px;border-bottom:1px solid #f3f3f3}}.pl:last-child{{border-bottom:none}}
.pl-tk{{font-family:'IBM Plex Mono',monospace;font-size:.88em;font-weight:600;color:var(--acc);width:42px;flex-shrink:0}}
.pl-desc{{font-size:.76em;color:#999;width:110px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.pl-bar-w{{flex:1;height:4px;background:#eee;border-radius:2px;overflow:hidden}}.pl-bar{{height:100%;border-radius:2px}}
.pl-val{{font-family:'IBM Plex Mono',monospace;font-size:.88em;font-weight:600;width:52px;text-align:right;flex-shrink:0}}
/* CAPITAL FLOW */
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.fc{{border:1px solid var(--brd2);padding:14px 16px;margin-bottom:8px;border-radius:3px;background:#fff}}.fi{{border-left:3px solid var(--p)}}.fo{{border-left:3px solid var(--n)}}
.fh{{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}}.fs{{font-weight:600;font-size:.92em}}.ft{{font-family:'IBM Plex Mono',monospace;font-size:.78em;color:#999}}
.fscore{{font-family:'IBM Plex Mono',monospace;font-size:.78em;padding:2px 8px;border-radius:2px;font-weight:600}}.fsp{{background:#eaf5ea;color:var(--p)}}.fsn{{background:#fceaea;color:var(--n)}}
.fm{{display:grid;grid-template-columns:repeat(4,1fr);gap:4px 10px;margin-bottom:8px;padding:8px 10px;background:#f8f8f8;border-radius:2px}}
.fmi{{display:flex;justify-content:space-between;align-items:center}}.fml{{font-size:.76em;color:#999}}.fmv{{font-family:'IBM Plex Mono',monospace;font-size:.82em;font-weight:500}}
.fd{{font-size:.82em;color:var(--tx2);line-height:1.5}}
/* TERMINAL */
.ax-wrap{{display:flex;gap:0;border:1px solid var(--brd);border-radius:3px;min-height:520px;background:#fff}}
.ax-side{{width:230px;border-right:1px solid var(--brd);background:#f8f8f8;flex-shrink:0;display:flex;flex-direction:column}}
.ax-ph{{font-family:'IBM Plex Mono',monospace;font-size:.7em;text-transform:uppercase;letter-spacing:1.5px;color:#999;padding:8px 10px;font-weight:500;border-bottom:1px solid var(--brd2)}}
.ax-tree{{flex:1;overflow-y:auto;font-size:.84em}}
.tr-sec{{border-bottom:1px solid var(--brd2)}}.tr-sh{{display:flex;align-items:center;gap:4px;padding:5px 8px;cursor:pointer;font-weight:600;font-size:.92em;user-select:none}}.tr-sh:hover{{background:#eee}}
.tr-sh input{{margin:0 3px 0 0}}.tr-arrow{{font-size:.6em;color:#999;width:12px;text-align:center;transition:transform .15s;display:inline-block}}.tr-arrow.open{{transform:rotate(90deg)}}
.tr-cnt{{font-weight:400;font-size:.78em;color:#bbb;margin-left:2px}}.tr-kids{{padding:0 0 2px 28px}}
.tr-tk{{display:block;padding:2px 6px;cursor:pointer;font-size:.92em}}.tr-tk:hover{{background:#eee}}.tr-tk input{{margin-right:4px}}.tr-d{{color:#999;font-size:.86em}}
.ax-clr{{font-family:'IBM Plex Mono',monospace;font-size:.72em;padding:8px;background:transparent;border:none;cursor:pointer;color:#999;text-transform:uppercase;letter-spacing:1px}}.ax-clr:hover{{background:#eee;color:#333}}
.ax-main{{flex:1;display:flex;flex-direction:column;min-width:0}}
.ax-top{{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--brd2);flex-wrap:wrap;gap:6px}}
.ax-legend{{display:flex;gap:10px;flex-wrap:wrap;font-size:.78em;flex:1}}.ax-legend span{{display:flex;align-items:center;gap:3px}}.ax-legend i{{width:14px;height:3px;display:inline-block}}
.ax-tf{{display:flex;gap:0}}.ax-tfb{{font-family:'IBM Plex Mono',monospace;font-size:.72em;padding:4px 12px;background:#f5f5f5;border:1px solid var(--brd2);cursor:pointer;color:#999;border-left:none}}.ax-tfb:first-child{{border-left:1px solid var(--brd2)}}
.ax-tfb:hover{{background:#eee;color:#333}}.ax-tfa{{background:#111!important;color:#fff!important;border-color:#111!important}}
.ax-cv-wrap{{position:relative;flex:1;min-height:360px}}.ax-cv-wrap canvas{{width:100%;height:100%;display:block}}
.ax-empty{{position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:.88em;flex-direction:column;gap:4px}}.ax-empty span{{font-size:.78em;color:#ccc}}
.ax-corr{{border-top:1px solid var(--brd);padding:14px 16px;background:#fafafa}}.ax-ch{{font-family:'IBM Plex Mono',monospace;font-size:.72em;text-transform:uppercase;letter-spacing:1.5px;color:#999;margin-bottom:10px}}
.cr-card{{background:#fff;border:1px solid var(--brd2);border-radius:3px;padding:12px 14px;margin-bottom:8px}}.cr-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.cr-pair{{font-weight:600;font-size:.92em;color:var(--acc)}}.cr-sig{{font-family:'IBM Plex Mono',monospace;font-size:.76em;text-transform:uppercase;letter-spacing:1px;padding:2px 8px;border-radius:2px}}.cr-sig.ru{{background:#eaf5ea}}.cr-sig.rd{{background:#fceaea}}.cr-sig.rz{{background:#f5f5f5}}
.cr-bars{{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}}.cr-bar-row{{display:flex;align-items:center;gap:8px}}
.cr-lbl{{font-family:'IBM Plex Mono',monospace;font-size:.72em;color:#999;width:20px;text-align:right;flex-shrink:0}}
.cr-bar-track{{flex:1;height:6px;background:#eee;border-radius:3px;overflow:hidden}}.cr-bar-fill{{height:100%;border-radius:3px}}
.cr-val{{font-family:'IBM Plex Mono',monospace;font-size:.84em;width:42px;text-align:right;flex-shrink:0}}
.cr-comment{{font-size:.82em;color:var(--tx2);line-height:1.55;padding:8px 10px;background:#f8f8f8;border-radius:2px;border-left:2px solid var(--brd)}}
.cr-lag{{display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px 10px;background:linear-gradient(90deg,#f0f4ff,#f8f0ff);border-radius:2px;border:1px solid #e0d8f0;font-size:.86em;color:#5c4d9a}}
/* NEWS */
.nw-info{{font-size:.82em;color:var(--tx2);margin-bottom:10px}}
.nw-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.nw-sec{{margin-bottom:14px}}
.nw-sec-hd{{font-family:'IBM Plex Mono',monospace;font-size:.72em;text-transform:uppercase;letter-spacing:1.2px;color:#999;padding:6px 0;border-bottom:2px solid var(--brd);margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}}
.nw-sec-cnt{{font-size:.85em;background:#eee;padding:1px 7px;border-radius:8px;letter-spacing:0}}
.nw-card{{border:1px solid var(--brd2);padding:10px 12px;margin-bottom:6px;border-radius:3px;background:#fff;border-left:3px solid #ccc;transition:border-color .15s}}.nw-card:hover{{border-left-color:#333}}
.nw-bull{{border-left-color:var(--p)}}.nw-bear{{border-left-color:var(--n)}}.nw-mix{{border-left-color:#D4AC0D}}
.nw-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:4px}}
.nw-hl{{font-size:.88em;font-weight:600;line-height:1.35;flex:1}}.nw-hl a{{color:var(--tx);text-decoration:none}}.nw-hl a:hover{{text-decoration:underline}}
.nw-imp{{font-family:'IBM Plex Mono',monospace;font-size:.72em;padding:2px 7px;border-radius:2px;font-weight:600;flex-shrink:0;white-space:nowrap}}
.nw-imp-b{{background:#eaf5ea;color:var(--p)}}.nw-imp-r{{background:#fceaea;color:var(--n)}}.nw-imp-m{{background:#fff8e1;color:#8B6914}}.nw-imp-n{{background:#f5f5f5;color:#999}}
.nw-sum{{font-size:.82em;color:var(--tx2);line-height:1.5;margin-bottom:5px}}.nw-meta{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.nw-src{{font-family:'IBM Plex Mono',monospace;font-size:.68em;color:#999}}.nw-etf{{display:inline-block;font-family:'IBM Plex Mono',monospace;font-size:.72em;padding:1px 6px;background:#f0f0f8;border-radius:2px;color:var(--acc);font-weight:600}}
.nw-rot{{border:1px solid #e8e0f8;background:#faf8ff;padding:8px 12px;border-radius:3px;margin-bottom:6px;font-size:.82em;color:#5c4d9a;line-height:1.5}}.nw-rot-icon{{margin-right:4px}}
/* FOOTER */
.foot{{border-top:1px solid var(--brd);padding:16px 0;margin-top:16px;text-align:center}}.disc{{font-size:.74em;color:#999;line-height:1.6}}.gen{{font-family:'IBM Plex Mono',monospace;font-size:.7em;color:#bbb}}
@media(max-width:900px){{.sidebar{{width:56px}}.sb-logo h1,.sb-logo .sub,.sb-item span:not(.sb-icon),.sb-meta{{display:none}}.sb-item{{padding:12px 0;justify-content:center}}.main{{margin-left:56px}}.g2,.pulse-grid,.nw-grid{{grid-template-columns:1fr}}.fm{{grid-template-columns:repeat(2,1fr)}}.ax-wrap{{flex-direction:column}}.ax-side{{width:100%;max-height:180px;border-right:none;border-bottom:1px solid var(--brd)}}}}
@media print{{.sidebar{{display:none}}.main{{margin-left:0}}.tab-content{{display:block!important}}}}
</style></head><body>

<!-- SIDEBAR -->
<nav class="sidebar">
<div class="sb-logo"><h1>ETF Dashboard</h1><div class="sub">Market Intelligence</div></div>
<div class="sb-nav">
<div class="sb-item active" onclick="showTab('overview')"><span class="sb-icon">\u25C8</span><span>Overview</span></div>
<div class="sb-item" onclick="showTab('sectors')"><span class="sb-icon">\u25A3</span><span>Sectors</span></div>
<div class="sb-item" onclick="showTab('countries')"><span class="sb-icon">\u25CB</span><span>Countries</span></div>
<div class="sb-item" onclick="showTab('news')"><span class="sb-icon">\u25C7</span><span>News</span></div>
<div class="sb-item" onclick="showTab('terminal')"><span class="sb-icon">\u25B7</span><span>Terminal</span></div>
</div>
<div class="sb-meta">{REPORT_DATE}<br>{AUTHOR}<br>{len(sec_nl)} sector ETFs<br>{len(reg_nl)} country ETFs<br>v5.0</div>
</nav>

<div class="main">
<div class="hd"><div class="hd-row"><div><h2 id="tab-title">Overview</h2><div class="sub2" id="tab-desc">Market snapshot, AI commentary, top signals</div></div><div class="hd-date">{REPORT_DATE}</div></div></div>

<!-- ═══════ TAB 1: OVERVIEW ═══════ -->
<div id="tab-overview" class="tab-content active">
<div class="krow">
<div class="ki"><div class="kl">SPY</div><div class="kv {"p" if spy["w1"]>=0 else "n"}">{spy["w1"]:+.2f}%</div><div class="kd">S&P 500</div></div>
<div class="ki"><div class="kl">QQQ</div><div class="kv {"p" if qqq["w1"]>=0 else "n"}">{qqq["w1"]:+.2f}%</div><div class="kd">Nasdaq 100</div></div>
<div class="ki"><div class="kl">Best</div><div class="kv p">{be["w1"]:+.1f}%</div><div class="kd">{be["ticker"]} {be["desc"]}</div></div>
<div class="ki"><div class="kl">Worst</div><div class="kv n">{we["w1"]:+.1f}%</div><div class="kd">{we["ticker"]} {we["desc"]}</div></div>
<div class="ki"><div class="kl">Breadth</div><div class="kv">{ps}/{len(sec_avgs)}</div><div class="kd">sectors positive</div></div>
<div class="ki"><div class="kl">Vol 21d</div><div class="kv {"n" if realized_vol>20 else "p" if realized_vol<15 else ""}">{realized_vol:.0f}%</div><div class="kd">SPY annualized</div></div>
<div class="ki"><div class="kl">Best Region</div><div class="kv p">{br[1]["w1"]:+.1f}%</div><div class="kd">{br[0]}</div></div>
</div>

<div class="krow" style="margin-bottom:8px">
<div class="ki"><div class="kl">Risk Score</div><div class="kv {"n" if risk_score>60 else "p" if risk_score<30 else ""}">{risk_score}/100</div><div class="kd">{"alto" if risk_score>60 else "basso" if risk_score<30 else "moderato"}</div></div>
<div class="ki"><div class="kl">Overbought</div><div class="kv">{pct_overbought}%</div><div class="kd">{n_overbought}/{n_total_rsi} ETF &gt; RSI 70</div></div>
<div class="ki"><div class="kl">Oversold</div><div class="kv">{pct_oversold}%</div><div class="kd">{n_oversold}/{n_total_rsi} ETF &lt; RSI 30</div></div>
<div class="ki"><div class="kl">Max DD 3M</div><div class="kv n">{dd_kpi_val}</div><div class="kd">{dd_kpi_desc}</div></div>
</div>

<div class="narr" id="narr-box">
<div class="nl">AI Market Analysis & Investment Ideas</div>
<div class="narr-ai">{'<div style="color:#444">' + narrative + '</div>' if not ai_commentary_html else ai_commentary_html}</div>
</div>

<div class="sec"><div class="card"><h3>Market Pulse</h3><div class="sd">Top 5 weekly movers and RSI extremes</div>
<div class="pulse-grid">
<div class="pulse-col"><div class="pulse-hd pulse-hd-gn">Top Gainers — 1W</div>{pulse_g}</div>
<div class="pulse-col"><div class="pulse-hd pulse-hd-ls">Top Losers — 1W</div>{pulse_l}</div>
<div class="pulse-col"><div class="pulse-hd pulse-hd-hi">Most Overbought</div>{pulse_rhi}</div>
<div class="pulse-col"><div class="pulse-hd pulse-hd-lo">Most Oversold</div>{pulse_rlo}</div>
</div></div></div>
{track_html}
</div>

<!-- ═══════ TAB 2: SECTORS ═══════ -->
<div id="tab-sectors" class="tab-content">
<div class="sec"><div class="card"><h3>Sector & ETF Performance</h3><div class="sd">Click sector to expand. Cell shading = relative magnitude.</div>
<div style="overflow-x:auto"><table><thead><tr><th>Sector / ETF</th><th>RSI</th><th>1W</th><th>1M</th><th>3M</th><th>1Y</th></tr></thead><tbody>{perf_html}</tbody></table></div></div></div>
<div class="sec"><div class="card"><h3>Sector Momentum</h3><div class="sd">Composite 0–100. Click to expand.</div>{sec_mom_html}</div></div>
<div class="sec"><div class="card"><h3>Capital Flow Signals — Sectors</h3><div class="sd">Volume-based inflow/outflow analysis</div>
<div class="g2"><div><h3 style="font-size:.84em;font-weight:600;margin-bottom:10px;color:var(--p)">Accumulation</h3>{sfi}</div>
<div><h3 style="font-size:.84em;font-weight:600;margin-bottom:10px;color:var(--n)">Distribution</h3>{sfo}</div></div></div></div>
</div>

<!-- ═══════ TAB 3: COUNTRIES ═══════ -->
<div id="tab-countries" class="tab-content">
<div class="sec"><div class="card"><h3>Region & Country ETF Performance</h3><div class="sd">Click region to expand. {len(reg_nl)} ETFs across {len(reg_avgs)} regions.</div>
<div style="overflow-x:auto"><table><thead><tr><th>Region / ETF</th><th>RSI</th><th>1W</th><th>1M</th><th>3M</th><th>1Y</th></tr></thead><tbody>{reg_perf_html}</tbody></table></div></div></div>
<div class="sec"><div class="card"><h3>Region Momentum</h3><div class="sd">Composite 0–100. Click to expand.</div>{reg_mom_html}</div></div>
<div class="sec"><div class="card"><h3>Capital Flow Signals — Regions</h3><div class="sd">Volume-based inflow/outflow analysis</div>
<div class="g2"><div><h3 style="font-size:.84em;font-weight:600;margin-bottom:10px;color:var(--p)">Accumulation</h3>{rfi}</div>
<div><h3 style="font-size:.84em;font-weight:600;margin-bottom:10px;color:var(--n)">Distribution</h3>{rfo}</div></div></div></div>
</div>

<!-- ═══════ TAB 4: NEWS ═══════ -->
<div id="tab-news" class="tab-content">
<div class="sec"><div class="card"><h3>Market Intelligence</h3><div class="sd">News mapped to ETF sectors with AI-powered impact analysis</div>
{news_html}</div></div>
</div>

<!-- ═══════ TAB 5: TERMINAL (sectors) ═══════ -->
<div id="tab-terminal" class="tab-content">
<div class="sec"><div class="card" style="padding:0">
<div style="padding:16px 20px 0"><h3>Analysis Terminal — Sectors</h3><div class="sd">All {len(SEC_ORDER)} sectors shown. Expand to add ETFs. Weekly, base 100.</div></div>
<div class="ax-wrap" id="term-sec">
<div class="ax-side">
<div class="ax-ph">Sectors</div>
<div class="ax-tree" id="tree-sec">{tree_sec}</div>
<div style="display:flex;border-top:1px solid var(--brd2)"><button class="ax-clr" style="flex:1" onclick="resetSel('sec')">Reset</button><button class="ax-clr" style="flex:1;border-left:1px solid var(--brd2)" onclick="clrSel('sec')">Clear</button></div>
</div>
<div class="ax-main">
<div class="ax-top"><div id="legend-sec" class="ax-legend"></div>
<div class="ax-tf"><button class="ax-tfb ax-tfa" data-tf="1y" onclick="setTf('sec','1y',this)">1Y</button><button class="ax-tfb" data-tf="5y" onclick="setTf('sec','5y',this)">5Y</button><button class="ax-tfb" data-tf="max" onclick="setTf('sec','max',this)">MAX</button></div></div>
<div class="ax-cv-wrap"><canvas id="cv-sec"></canvas><div id="empty-sec" class="ax-empty">Select assets<span>Click sector to expand</span></div></div>
<div id="corr-sec" class="ax-corr" style="display:none"><div class="ax-ch">Correlation Analysis</div><div id="corr-body-sec"></div></div>
</div></div></div></div>

<div class="sec"><div class="card" style="padding:0">
<div style="padding:16px 20px 0"><h3>Analysis Terminal — Countries</h3><div class="sd">All 8 regions shown. Expand to add ETFs.</div></div>
<div class="ax-wrap" id="term-reg">
<div class="ax-side">
<div class="ax-ph">Regions</div>
<div class="ax-tree" id="tree-reg">{tree_reg}</div>
<div style="display:flex;border-top:1px solid var(--brd2)"><button class="ax-clr" style="flex:1" onclick="resetSel('reg')">Reset</button><button class="ax-clr" style="flex:1;border-left:1px solid var(--brd2)" onclick="clrSel('reg')">Clear</button></div>
</div>
<div class="ax-main">
<div class="ax-top"><div id="legend-reg" class="ax-legend"></div>
<div class="ax-tf"><button class="ax-tfb ax-tfa" data-tf="1y" onclick="setTf('reg','1y',this)">1Y</button><button class="ax-tfb" data-tf="5y" onclick="setTf('reg','5y',this)">5Y</button><button class="ax-tfb" data-tf="max" onclick="setTf('reg','max',this)">MAX</button></div></div>
<div class="ax-cv-wrap"><canvas id="cv-reg"></canvas><div id="empty-reg" class="ax-empty">Select assets<span>Click region to expand</span></div></div>
</div></div></div></div>
</div>

<div class="foot"><div class="disc">Automatically generated for informational purposes only. Not financial advice.</div><p class="gen">{datetime.now().strftime("%Y-%m-%d %H:%M")} &middot; v5.0</p></div>
</div>

<script>
var DS={chart_sec_json};
var DR={chart_reg_json};
var CC={corr_comments_json};
var C=["#111","#e84855","#147","#a14","#1a6b4a","#b08030","#417","#714","#471","#941","#194","#491"];
var TF_WEEKS={{'1y':52,'5y':260,'max':9999}};
var state={{sec:{{sel:[],tf:'1y'}},reg:{{sel:[],tf:'1y'}}}};

function showTab(id){{
  document.querySelectorAll('.tab-content').forEach(function(t){{t.classList.remove('active')}});
  document.getElementById('tab-'+id).classList.add('active');
  document.querySelectorAll('.sb-item').forEach(function(s){{s.classList.remove('active')}});
  event.currentTarget.classList.add('active');
  var titles={{'overview':['Overview','Market snapshot, AI commentary, top signals'],'sectors':['Sectors','{len(sec_nl)} sector ETFs performance, momentum, capital flows'],'countries':['Countries','8 regions, 54 country ETFs performance & momentum'],'news':['News','Market intelligence from top-tier financial sources'],'terminal':['Terminal','Interactive charting with correlation analysis']}};
  var t=titles[id]||['',''];
  document.getElementById('tab-title').textContent=t[0];
  document.getElementById('tab-desc').textContent=t[1];
  if(id==='terminal'){{setTimeout(function(){{drawChart('sec');drawChart('reg')}},50)}}
}}

function tgl(id){{var rows=document.querySelectorAll('.g_'+id);var a=document.getElementById('a_'+id);var show=rows.length>0&&rows[0].style.display==='none';rows.forEach(function(r){{r.style.display=show?'':'none'}});if(a)a.textContent=show?'\u2212':'+'}}
function togSec(sid,ev){{if(ev.target.tagName==='INPUT')return;var k=document.getElementById('tk_'+sid);var a=document.getElementById('ta_'+sid);if(k.style.display==='none'){{k.style.display='';a.classList.add('open')}}else{{k.style.display='none';a.classList.remove('open')}}}}

function secCb(el,gid){{if(!el.checked){{document.querySelectorAll('#tk_'+gid+' input').forEach(function(k){{k.checked=false}})}}updSel(gid.startsWith('C')?'reg':'sec')}}
function secCbC(el,gid){{secCb(el,gid)}}
function upd(){{updSel('sec')}}
function updC(){{updSel('reg')}}

function updSel(which){{
  var D=which==='sec'?DS:DR;var grpKey=which==='sec'?'sectors':'regions';
  var treeId=which==='sec'?'tree-sec':'tree-reg';
  state[which].sel=[];
  document.querySelectorAll('#'+treeId+' .tr-sh input:checked').forEach(function(i){{
    var s=i.value.replace('S:','');
    if(D[grpKey][s])state[which].sel.push({{name:s,prices:D[grpKey][s],type:'group',key:s}});
  }});
  document.querySelectorAll('#'+treeId+' .tr-tk input:checked').forEach(function(i){{
    var t=i.value;if(!D.tickers[t])return;
    state[which].sel.push({{name:t,prices:D.tickers[t].p,type:'ticker',key:D.tickers[t].s,desc:D.tickers[t].d}});
  }});
  drawChart(which);if(which==='sec')showCorr(which);
}}

function clrSel(w){{document.querySelectorAll('#tree-'+(w==='sec'?'sec':'reg')+' input').forEach(function(i){{i.checked=false}});state[w].sel=[];drawChart(w);if(w==='sec')showCorr(w)}}
function resetSel(w){{
  var tid='tree-'+(w==='sec'?'sec':'reg');
  document.querySelectorAll('#'+tid+' input').forEach(function(i){{i.checked=false}});
  document.querySelectorAll('#'+tid+' .tr-sh input').forEach(function(i){{i.checked=true}});
  document.querySelectorAll('#'+tid+' .tr-kids').forEach(function(k){{k.style.display='none'}});
  document.querySelectorAll('#'+tid+' .tr-arrow').forEach(function(a){{a.classList.remove('open')}});
  updSel(w);
}}
function setTf(w,t,btn){{state[w].tf=t;btn.parentElement.querySelectorAll('.ax-tfb').forEach(function(b){{b.classList.remove('ax-tfa')}});btn.classList.add('ax-tfa');drawChart(w)}}

function drawChart(w){{
  var D=w==='sec'?DS:DR;var sel=state[w].sel;var tf=state[w].tf;
  var cv=document.getElementById('cv-'+w);var ctx=cv.getContext('2d');
  var wrap=cv.parentElement;var emp=document.getElementById('empty-'+w);var leg=document.getElementById('legend-'+w);
  var W=wrap.clientWidth;var H=Math.max(360,wrap.clientHeight);cv.width=W;cv.height=H;ctx.clearRect(0,0,W,H);
  if(sel.length===0){{emp.style.display='flex';leg.innerHTML='';return}}emp.style.display='none';
  var maxW=TF_WEEKS[tf]||52;
  var series=sel.map(function(s){{var p=s.prices;var n=Math.min(maxW+1,p.length);var sl=p.slice(p.length-n);var b=sl[0]||1;return sl.map(function(v){{return v/b*100}})}});
  var nPts=Math.min.apply(null,series.map(function(s){{return s.length}}));
  series=series.map(function(s){{return s.slice(s.length-nPts)}});
  var startMs=new Date(D.startDate).getTime();var tw=D.numWeeks;
  var pad={{l:50,r:68,t:16,b:40}};var cw=W-pad.l-pad.r;var ch=H-pad.t-pad.b;
  var allP=[];series.forEach(function(s){{s.forEach(function(v){{allP.push(v)}})}});
  var mn=Math.min.apply(null,allP);var mx=Math.max.apply(null,allP);
  var range=mx-mn;if(range<2)range=4;mn-=range*.05;mx+=range*.05;range=mx-mn;
  ctx.fillStyle='#fcfcfc';ctx.fillRect(pad.l,pad.t,cw,ch);
  ctx.font='10px IBM Plex Mono';
  for(var i=0;i<=5;i++){{var y=pad.t+ch*(1-i/5);var v=mn+range*i/5;ctx.strokeStyle=i===0?'#ccc':'#eee';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();ctx.fillStyle='#999';ctx.textAlign='right';ctx.fillText(v.toFixed(0),pad.l-6,y+3)}}
  var step=Math.max(1,Math.floor(nPts/6));ctx.textAlign='center';ctx.font='9px IBM Plex Mono';
  var months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmtD(i){{var d=new Date(startMs+(tw-nPts+i)*7*86400000);return months[d.getMonth()]+' '+String(d.getFullYear()).slice(2)}}
  for(var i=0;i<nPts;i+=step){{var x=pad.l+cw*i/(nPts-1||1);if(i>0){{ctx.strokeStyle='#f0f0f0';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,pad.t);ctx.lineTo(x,pad.t+ch);ctx.stroke()}}ctx.fillStyle='#999';ctx.fillText(fmtD(i),x,H-pad.b+14)}}
  if(mn<100&&mx>100){{var y100=pad.t+ch*(1-(100-mn)/range);ctx.strokeStyle='#aaa';ctx.lineWidth=0.7;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(pad.l,y100);ctx.lineTo(W-pad.r,y100);ctx.stroke();ctx.setLineDash([])}}
  var legH='';
  sel.forEach(function(s,si){{
    var pts=series[si];var c=C[si%C.length];
    ctx.strokeStyle=c;ctx.lineWidth=s.type==='group'?2.2:1.5;
    if(s.type==='ticker')ctx.setLineDash([5,3]);else ctx.setLineDash([]);
    ctx.beginPath();for(var i=0;i<nPts;i++){{var x=pad.l+cw*i/(nPts-1||1);var y=pad.t+ch*(1-(pts[i]-mn)/range);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)}}
    ctx.stroke();ctx.setLineDash([]);
    var lv=pts[nPts-1];var ret=lv-100;var lx=pad.l+cw;var ly=pad.t+ch*(1-(lv-mn)/range);
    ctx.fillStyle=c;ctx.beginPath();ctx.arc(lx,ly,3,0,Math.PI*2);ctx.fill();
    ctx.font='10px IBM Plex Mono';ctx.textAlign='left';ctx.fillText(lv.toFixed(0),lx+6,ly-3);
    ctx.fillStyle=ret>=0?'#1a6b4a':'#8b1a1a';ctx.font='9px IBM Plex Mono';ctx.fillText((ret>=0?'+':'')+ret.toFixed(1)+'%',lx+6,ly+9);
    var label=s.desc?s.name+' ('+s.desc+')':s.name;
    legH+='<span><i style="background:'+c+'"></i>'+label+'</span>';
  }});leg.innerHTML=legH;
}}

function showCorr(w){{
  var box=document.getElementById('corr-'+w);var body=document.getElementById('corr-body-'+w);
  if(!box)return;var sel=state[w].sel;
  if(sel.length<2){{box.style.display='none';return}}box.style.display='block';
  var h='';var seen={{}};var found=0;
  for(var i=0;i<sel.length;i++){{for(var j=i+1;j<sel.length;j++){{
    var a=sel[i].key,b=sel[j].key;if(a===b)continue;var pk=a<b?a+'|'+b:b+'|'+a;if(seen[pk])continue;seen[pk]=1;
    var cd=DS.corr[a+'|'+b]||DS.corr[b+'|'+a];if(!cd)continue;found++;
    var d=cd.m3-cd.y3;var sig=d>0.05?'converging':d<-0.05?'diverging':'stable';var sigCls=d>0.05?'ru':d<-0.05?'rd':'rz';
    var y3w=Math.abs(cd.y3)*100;var m3w=Math.abs(cd.m3)*100;
    var y3c=cd.y3>0.3?'var(--p)':cd.y3<-0.1?'var(--n)':'#aaa';
    var m3c=cd.m3>0.3?'var(--p)':cd.m3<-0.1?'var(--n)':'#aaa';
    var ckey=a<b?a+'|'+b:b+'|'+a;var comment=CC[ckey]||CC[b+'|'+a]||'';
    h+='<div class="cr-card"><div class="cr-head"><span class="cr-pair">'+sel[i].name+' \u2014 '+sel[j].name+'</span><span class="'+sigCls+' cr-sig">'+sig+'</span></div>';
    if(cd.leader&&cd.lag_w>=3){{h+='<div class="cr-lag">\u23F1\uFE0F '+cd.leader+' \u279C '+cd.follower+' ('+cd.lag_w+'w, \u03C1='+cd.lag_r.toFixed(2)+')</div>'}}
    h+='<div class="cr-bars"><div class="cr-bar-row"><span class="cr-lbl">3Y</span><div class="cr-bar-track"><div class="cr-bar-fill" style="width:'+y3w+'%;background:'+y3c+'"></div></div><span class="cr-val" style="color:'+y3c+'">'+cd.y3.toFixed(2)+'</span></div>';
    h+='<div class="cr-bar-row"><span class="cr-lbl">3M</span><div class="cr-bar-track"><div class="cr-bar-fill" style="width:'+m3w+'%;background:'+m3c+'"></div></div><span class="cr-val" style="color:'+m3c+'">'+cd.m3.toFixed(2)+'</span></div>';
    h+='<div class="cr-bar-row"><span class="cr-lbl">\u0394</span><div style="flex:1"></div><span class="cr-val '+(d>0?'p':'n')+'" style="font-weight:600">'+(d>0?'+':'')+d.toFixed(2)+'</span></div></div>';
    if(comment)h+='<div class="cr-comment">'+comment+'</div>';
    h+='</div>';
  }}}}
  if(!found)h='<div style="color:#999;font-size:.84em">No correlation data for this selection.</div>';
  body.innerHTML=h;
}}

window.addEventListener('resize',function(){{drawChart('sec');drawChart('reg')}});
window.addEventListener('DOMContentLoaded',function(){{updSel('sec');updSel('reg')}});
</script>
</body></html>'''

# Write output
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ETF_Report.html')
with open(out, 'w', encoding='utf-8') as f: f.write(html)

# Validation
ok = all(len(re.findall(f'<{t}[\\s>]',html))==len(re.findall(f'</{t}>',html)) for t in ['div','table','thead','tbody','tr','td','th','span','canvas','label','nav'])
print(f"\n{'='*60}")
print(f"  Dashboard -> {out}")
print(f"  {len(html):,} bytes, HTML {'valid' if ok else 'CHECK'}")
print(f"  {len(sec_nl)} sector ETFs, {len(reg_nl)} country ETFs")
print(f"  News: {'integrated' if NEWS else 'not available'}")
print(f"{'='*60}")
