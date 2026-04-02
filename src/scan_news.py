"""
MIS - Market Intelligence Scanner (Lightweight)
Scans top-tier financial sources, classifies by ETF sector, outputs JSON for dashboard integration.

Max 50 articles. ~15 feeds. Fast execution (< 60s with LLM, < 10s without).
Output: news_data.json (same directory) — consumed by build_v3.py / build_v4.py

Requirements: pip install feedparser requests beautifulsoup4 pandas groq
"""

import subprocess, sys, os, importlib, importlib.util

REQUIRED = {'feedparser':'feedparser','requests':'requests','bs4':'beautifulsoup4','pandas':'pandas','groq':'groq'}
def ensure_deps():
    missing = [p for i,p in REQUIRED.items() if not importlib.util.find_spec(i)]
    if missing:
        print(f"[setup] Installing: {', '.join(missing)}")
        subprocess.check_call([sys.executable,'-m','pip','install','--quiet']+missing)
ensure_deps()

import requests, feedparser, pandas as pd, time, re, json, ssl, warnings
import urllib.request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from groq import Groq

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
__import__('logging').getLogger('urllib3').setLevel(__import__('logging').WARNING)

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except: pass

def safe_print(text):
    try: print(text)
    except UnicodeEncodeError: print(text.encode('ascii',errors='replace').decode('ascii'))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# ╔═══════════════════════════════════════════════════════════╗
# ║  ETF UNIVERSE (same as build_v3.py / build_v4.py)       ║
# ╚═══════════════════════════════════════════════════════════╝
ETF_SECTORS = {
    "Broad Market":         ["SPY","QQQ","DIA","VTI","IWM"],
    "International":        ["EEM","EFA","KWEB"],
    "Tech & Semiconductors":["XLK","VGT","ARKK","BOTZ","SMH","HACK","CIBR","SKYY","CLOU"],
    "Healthcare":           ["XLV","XBI","IBB","ARKG"],
    "Financials":           ["XLF","FINX"],
    "Energy":               ["XLE","USO","URA","TAN","ICLN","QCLN"],
    "Commodities":          ["XLB","COPX","REMX","SLV","GLD","GDX"],
    "Real Estate":          ["XLRE","VNQ","ITB","XHB","PAVE"],
    "Industrials":          ["XLI","JETS","DRIV","IDRV","ITA","UFO","ARKX"],
    "Bonds":                ["TLT","HYG","LQD"],
    "Crypto":               ["BITO","BLOK"],
    "Consumers":            ["XLP","XLY","XLU","XLC","ESPO"],
}
SECTOR_ORDER = list(ETF_SECTORS.keys())
ALL_TICKERS = sorted(set(tk for tks in ETF_SECTORS.values() for tk in tks))
TICKER_TO_SECTOR = {tk:s for s,tks in ETF_SECTORS.items() for tk in tks}

# ╔═══════════════════════════════════════════════════════════╗
# ║  CONFIGURATION                                          ║
# ╚═══════════════════════════════════════════════════════════╝
MAX_ARTICLES = 50
LOOKBACK_DAYS = 7
FALLBACK_DAYS = 10
TIMEOUT = 12
MAX_WORKERS = 8
USER_AGENT = 'MIS/2.0'
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'news_data.json')

# LLM
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
LLM_MODEL = 'llama-3.3-70b-versatile'
LLM_ENABLED = bool(GROQ_API_KEY)
LLM_DELAY = 2.0
LLM_RETRIES = 2

_sector_list = ", ".join(SECTOR_ORDER)

LLM_SYSTEM_PROMPT = f"""Sei un analista senior di market intelligence per un desk ETF istituzionale.
Il nostro universo di investimento copre 12 settori: {_sector_list}

Analizza la notizia e rispondi SOLO con JSON valido:
{{
  "sectors": ["Tech & Semiconductors", "Broad Market"],
  "etf_tickers": ["SMH", "QQQ"],
  "relevance": 7,
  "headline_it": "Titolo in italiano max 10 parole",
  "summary_it": "1-2 frasi in italiano sull'impatto per ETF/settori.",
  "impact": "bearish",
  "rotation": ""
}}

REGOLE:
- "sectors": solo nomi dalla lista sopra. Anche multipli.
- "etf_tickers": max 4, solo dal nostro universo.
- "relevance": 1-10 (8+ = market-moving, 5-7 = significativo, 3-4 = background, 1-2 = rumore)
- "impact": "bullish" | "bearish" | "neutral" | "mixed"
- "rotation": eventuale segnale di rotazione settoriale (stringa vuota se non applicabile)
- headline e summary SEMPRE in italiano
"""

# ╔═══════════════════════════════════════════════════════════╗
# ║  TOP-TIER FEEDS ONLY (~15 feeds, highest signal/noise)  ║
# ╚═══════════════════════════════════════════════════════════╝
FEEDS = [
    # Tier 1 — Central Banks (market-moving by definition)
    ('Federal Reserve',     'https://www.federalreserve.gov/feeds/press_all.xml',           10),
    ('ECB',                 'https://www.ecb.europa.eu/rss/press.html',                     10),
    ('Bank of England',     'https://www.bankofengland.co.uk/rss/news',                      9),
    ('Bank of Japan',       'https://www.boj.or.jp/en/rss/whatsnew.xml',                     9),

    # Tier 1 — International Institutions
    ('IMF',                 'https://www.imf.org/en/rss-list/feed?category=WHATSNEW',        9),
    ('BIS',                 'https://www.bis.org/doclist/all_pressrels.rss',                  8),

    # Tier 1 — Premium Financial News (broad market + breaking)
    ('CNBC Economy',        'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258', 8),
    ('CNBC Finance',        'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664', 8),
    ('CNBC World',          'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362', 8),
    ('MarketWatch',         'https://feeds.content.dowjones.io/public/rss/mw_topstories',   8),
    ('MarketWatch Markets', 'https://feeds.content.dowjones.io/public/rss/mw_marketpulse',  8),
    ('Seeking Alpha',       'https://seekingalpha.com/market_currents.xml',                  7),
    ('Reuters',             'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best', 9),

    # Tier 1 — GEOPOLITICS & BREAKING NEWS (critical for market-moving events)
    ('BBC World',           'http://feeds.bbci.co.uk/news/world/rss.xml',                    8),
    ('Al Jazeera',          'https://www.aljazeera.com/xml/rss/all.xml',                     8),
    ('Foreign Policy',      'https://foreignpolicy.com/feed/',                               7),
    ('Defense One',         'https://www.defenseone.com/rss/',                               7),

    # Tier 2 — Sector-specific high-value
    ('Finextra',            'https://www.finextra.com/rss/headlines.aspx',                   6),
    ('OilPrice',            'https://oilprice.com/rss/main',                                 7),
    ('SemiEngineering',     'https://semiengineering.com/feed/',                              6),

    # Tier 2 — Asia & Emerging Markets
    ('Nikkei Asia',         'https://asia.nikkei.com/rss',                                   7),
    ('SCMP',                'https://www.scmp.com/rss/2/feed',                               7),
]

# ╔═══════════════════════════════════════════════════════════╗
# ║  KEYWORD MAP — sector-aligned, compact                  ║
# ╚═══════════════════════════════════════════════════════════╝
# Each keyword maps to one or more ETF sectors
KEYWORD_SECTORS = {
    # Broad Market & Macro
    'interest rate': ['Broad Market','Bonds'], 'rate decision': ['Broad Market','Bonds'],
    'rate hike': ['Broad Market','Bonds','Financials'], 'rate cut': ['Broad Market','Bonds','Real Estate'],
    'inflation': ['Broad Market','Bonds','Commodities'], 'CPI': ['Broad Market','Bonds'],
    'GDP': ['Broad Market'], 'recession': ['Broad Market','Bonds'],
    'unemployment': ['Broad Market'], 'non-farm payroll': ['Broad Market'],
    'monetary policy': ['Broad Market','Bonds'], 'quantitative': ['Broad Market','Bonds'],
    'yield curve': ['Bonds','Financials'], 'treasury': ['Bonds'],
    'PMI': ['Broad Market','Industrials'], 'consumer confidence': ['Consumers','Broad Market'],
    'stock market': ['Broad Market'], 'S&P 500': ['Broad Market'], 'Nasdaq': ['Broad Market','Tech & Semiconductors'],
    'VIX': ['Broad Market'], 'volatility': ['Broad Market'],
    # Tech
    'artificial intelligence': ['Tech & Semiconductors'], 'semiconductor': ['Tech & Semiconductors'],
    'chip': ['Tech & Semiconductors'], 'NVIDIA': ['Tech & Semiconductors'],
    'TSMC': ['Tech & Semiconductors'], 'cloud computing': ['Tech & Semiconductors'],
    'cybersecurity': ['Tech & Semiconductors'], 'data center': ['Tech & Semiconductors'],
    'Apple': ['Tech & Semiconductors','Consumers'], 'Microsoft': ['Tech & Semiconductors'],
    'Google': ['Tech & Semiconductors','Consumers'], 'Amazon': ['Tech & Semiconductors','Consumers'],
    'Meta': ['Tech & Semiconductors','Consumers'],
    # Healthcare
    'biotech': ['Healthcare'], 'pharmaceutical': ['Healthcare'], 'FDA': ['Healthcare'],
    'drug approval': ['Healthcare'], 'clinical trial': ['Healthcare'],
    'GLP-1': ['Healthcare'], 'Ozempic': ['Healthcare'],
    # Financials
    'bank': ['Financials'], 'fintech': ['Financials'], 'JPMorgan': ['Financials'],
    'Goldman': ['Financials'], 'credit': ['Financials','Bonds'],
    'digital payments': ['Financials'], 'CBDC': ['Financials','Crypto'],
    # Energy
    'oil': ['Energy','Commodities'], 'crude': ['Energy'], 'OPEC': ['Energy'],
    'natural gas': ['Energy'], 'LNG': ['Energy'], 'solar': ['Energy'],
    'nuclear': ['Energy'], 'uranium': ['Energy'], 'clean energy': ['Energy'],
    'renewable': ['Energy'], 'energy transition': ['Energy'],
    # Commodities
    'gold': ['Commodities'], 'silver': ['Commodities'], 'copper': ['Commodities'],
    'lithium': ['Commodities'], 'rare earth': ['Commodities'], 'mining': ['Commodities'],
    'commodity': ['Commodities'], 'iron ore': ['Commodities'],
    # Real Estate
    'housing': ['Real Estate'], 'mortgage': ['Real Estate','Bonds'],
    'REIT': ['Real Estate'], 'infrastructure': ['Real Estate','Industrials'],
    'homebuilder': ['Real Estate'],
    # Industrials
    'aerospace': ['Industrials'], 'defense': ['Industrials'],
    'airline': ['Industrials'], 'electric vehicle': ['Industrials'],
    'EV': ['Industrials'], 'Boeing': ['Industrials'], 'manufacturing': ['Industrials'],
    # Bonds
    'bond': ['Bonds'], 'fixed income': ['Bonds'], 'credit spread': ['Bonds','Financials'],
    'high yield': ['Bonds'], 'investment grade': ['Bonds'],
    # Crypto
    'bitcoin': ['Crypto'], 'crypto': ['Crypto'], 'blockchain': ['Crypto'],
    'ethereum': ['Crypto'], 'Coinbase': ['Crypto'],
    # Consumers
    'retail sales': ['Consumers'], 'consumer spending': ['Consumers'],
    'luxury': ['Consumers'], 'gaming': ['Consumers'],
    'Netflix': ['Consumers'], 'Disney': ['Consumers'],
    # International / Geopolitics
    'tariff': ['International','Broad Market'], 'sanctions': ['International','Energy'],
    'trade war': ['International','Broad Market'], 'geopolitical': ['International'],
    'China': ['International'], 'India': ['International'],
    'emerging market': ['International'], 'election': ['International','Broad Market'],
    'conflict': ['International'], 'NATO': ['International','Industrials'],
    'BRICS': ['International','Commodities'],
    # Middle East / Military conflicts (critical for oil, defense, risk-off)
    'Iran': ['International','Energy','Commodities','Industrials'],
    'Israel': ['International','Energy','Industrials'],
    'military': ['International','Industrials'], 'missile': ['International','Industrials'],
    'attack': ['International','Broad Market'], 'war': ['International','Broad Market','Energy','Commodities'],
    'combat': ['International','Broad Market','Energy'],
    'airstrike': ['International','Industrials','Energy'],
    'retaliation': ['International','Energy','Broad Market'],
    'Middle East': ['International','Energy'],
    'Tehran': ['International','Energy'], 'Gulf': ['International','Energy'],
    'OPEC': ['Energy','International'], 'Strait of Hormuz': ['Energy','International'],
    'oil shock': ['Energy','Commodities','Broad Market'],
    'safe haven': ['Commodities','Bonds'], 'risk-off': ['Broad Market','Bonds','Commodities'],
    'flight to safety': ['Bonds','Commodities'],
    'defense spending': ['Industrials'], 'arms': ['Industrials'],
    'Lockheed': ['Industrials'], 'Raytheon': ['Industrials'], 'Northrop': ['Industrials'],
    'nuclear': ['Energy','International'], 'uranium': ['Energy'],
    'ceasefire': ['International','Energy'], 'escalation': ['International','Energy','Broad Market'],
    'invasion': ['International','Broad Market','Energy','Commodities'],
    'regime change': ['International'], 'coup': ['International'],
    'Taiwan': ['International','Tech & Semiconductors'],
    'South Korea': ['International','Tech & Semiconductors'],
    'Ukraine': ['International','Energy','Commodities'],
    'Russia': ['International','Energy','Commodities'],
}

# ╔═══════════════════════════════════════════════════════════╗
# ║  FUNCTIONS                                              ║
# ╚═══════════════════════════════════════════════════════════╝
_ctx = ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = ssl.CERT_NONE
_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx))

def _session():
    s = requests.Session(); s.verify = False; s.headers['User-Agent'] = USER_AGENT
    a = HTTPAdapter(max_retries=Retry(total=1,backoff_factor=0.3,status_forcelist=[429,500,502,503,504],allowed_methods=['GET']))
    s.mount('http://',a); s.mount('https://',a); return s

HTTP = _session()

def parse_feed(url):
    try:
        r = _opener.open(url, timeout=TIMEOUT)
        f = feedparser.parse(r.read())
        return f.get('entries',[])
    except:
        try: return feedparser.parse(url).get('entries',[])
        except: return []

def parse_all():
    results = {}
    def _do(name, url, tier):
        return name, tier, parse_feed(url)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_do, n, u, t): n for n,u,t in FEEDS}
        for f in as_completed(futs):
            try:
                name, tier, entries = f.result()
                if name not in results: results[name] = {'tier': tier, 'entries': []}
                results[name]['entries'].extend(entries)
            except: pass
    return results

def parse_date(entry):
    for k in ['published_parsed','updated_parsed','created_parsed']:
        if k in entry and entry[k]:
            try:
                t = entry[k]
                return datetime(t.tm_year,t.tm_mon,t.tm_mday,t.tm_hour,t.tm_min,t.tm_sec,tzinfo=timezone.utc)
            except: pass
    return None

def clean_html(text):
    return re.sub(r'<[^>]*>','',text) if isinstance(text,str) else ''

def scrape_summary(url):
    try:
        r = HTTP.get(url, timeout=TIMEOUT)
        if r.status_code==200 and 'html' in r.headers.get('content-type',''):
            soup = BeautifulSoup(r.text, 'html.parser')
            for attr in ['og:description','description','twitter:description']:
                m = soup.find('meta',attrs={'property':re.compile(f'^{attr}$',re.I)}) or soup.find('meta',attrs={'name':re.compile(f'^{attr}$',re.I)})
                if m and m.get('content'): return m['content']
    except: pass
    return ''

def detect_etf_tickers(text):
    """Find ETF tickers mentioned in text."""
    found = []
    for tk in ALL_TICKERS:
        if re.search(r'(?<![A-Za-z])' + re.escape(tk) + r'(?![A-Za-z])', text):
            found.append(tk)
    return found

def detect_sentiment(title, summary):
    """Keyword-based sentiment when LLM unavailable."""
    text = (title + ' ' + summary).lower()
    bull = ['rally','surge','soar','beat','upside','upgrade','bullish','growth',
            'recovery','record high','outperform','boom','gain','positive','strong',
            'optimism','dovish','stimulus','easing','rate cut','rebound','breakout']
    bear = ['crash','plunge','sell-off','selloff','downgrade','bearish','decline',
            'recession','layoff','default','bankrupt','slump','collapse','loss',
            'miss','negative','weak','warning','crisis','hawkish','tightening',
            'rate hike','correction','downturn','fear','risk-off','drop','fall']
    b = sum(1 for w in bull if w in text)
    r = sum(1 for w in bear if w in text)
    if b >= 2 and r == 0: return 'bullish'
    if r >= 2 and b == 0: return 'bearish'
    if b >= 1 and r >= 1: return 'mixed'
    if b >= 1: return 'bullish'
    if r >= 1: return 'bearish'
    return 'neutral'

def classify_by_keywords(title, summary):
    """Return set of sectors matched by keywords."""
    text = (title + ' ' + summary).lower()
    sectors = set()
    matched_kw = []
    for kw, secs in KEYWORD_SECTORS.items():
        if kw.lower() in text:
            sectors.update(secs)
            matched_kw.append(kw)
    return sorted(sectors), matched_kw

def score_article(source_tier, sectors, matched_kw, title, summary, etf_tickers):
    """Quick relevance score 1-10 based on source tier + keyword quality."""
    score = source_tier  # base from source (6-10)
    # Keyword density bonus
    score += min(len(matched_kw) * 0.3, 2.0)
    # Multi-sector = broader impact
    if len(sectors) >= 3: score += 1.0
    # Direct ETF ticker mention
    if etf_tickers: score += min(len(etf_tickers) * 0.5, 1.5)
    # High-value keyword boost
    text = (title + ' ' + summary).lower()
    hv = ['rate decision','rate cut','rate hike','recession','tariff','sanctions',
          'OPEC','semiconductor','invasion','inflation surprise','earnings',
          'Iran','attack','military','war','missile','combat','airstrike',
          'retaliation','nuclear','ceasefire','oil shock','regime change',
          'Strait of Hormuz','escalation']
    for h in hv:
        if h.lower() in text: score += 0.5
    return min(round(score, 1), 10.0)


def llm_enrich(articles):
    """Enrich top articles with LLM analysis. Returns enriched list."""
    if not LLM_ENABLED:
        safe_print("  LLM: skipped (no key)")
        return articles

    try: client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        safe_print(f"  LLM error: {e}"); return articles

    # Only LLM-analyze top articles (by score), max 25 to stay within rate limits
    sorted_arts = sorted(articles, key=lambda a: a['score'], reverse=True)
    to_analyze = sorted_arts[:min(25, len(sorted_arts))]
    analyzed_links = set()

    safe_print(f"  LLM: analyzing {len(to_analyze)} articles...")
    for i, art in enumerate(to_analyze):
        if art['link'] in analyzed_links: continue
        analyzed_links.add(art['link'])

        short = art['title'][:50] + ('...' if len(art['title'])>50 else '')
        safe_print(f"    [{i+1}/{len(to_analyze)}] {short}")

        msg = f"Source: {art['source']}\nTitle: {art['title']}\nSummary: {art['summary'][:800]}"
        for attempt in range(LLM_RETRIES + 1):
            try:
                resp = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role":"system","content":LLM_SYSTEM_PROMPT},{"role":"user","content":msg}],
                    temperature=0.15, max_tokens=400,
                    response_format={"type":"json_object"},
                )
                r = json.loads(resp.choices[0].message.content)
                art['llm'] = {
                    'sectors': [s for s in r.get('sectors',[]) if s in SECTOR_ORDER],
                    'etf_tickers': [t for t in r.get('etf_tickers',[]) if t in ALL_TICKERS],
                    'relevance': max(1,min(10,int(r.get('relevance',5)))),
                    'headline_it': r.get('headline_it',''),
                    'summary_it': r.get('summary_it',''),
                    'impact': r.get('impact','neutral'),
                    'rotation': r.get('rotation',''),
                }
                # Blend LLM relevance with keyword score
                art['score'] = round(0.35 * art['score'] + 0.65 * art['llm']['relevance'], 1)
                # Merge sectors
                art['sectors'] = sorted(set(art['sectors'] + art['llm']['sectors']))
                art['etf_tickers'] = sorted(set(art['etf_tickers'] + art['llm']['etf_tickers']))
                break
            except Exception as e:
                if '429' in str(e) or 'rate' in str(e).lower():
                    time.sleep(LLM_DELAY * (2**attempt)); continue
                if attempt < LLM_RETRIES: time.sleep(LLM_DELAY); continue
                break

        if i < len(to_analyze)-1: time.sleep(LLM_DELAY)

    # Propagate LLM data to all articles with same link
    llm_map = {a['link']: a.get('llm') for a in to_analyze if a.get('llm')}
    for art in articles:
        if art['link'] in llm_map and 'llm' not in art:
            art['llm'] = llm_map[art['link']]

    return articles


# ╔═══════════════════════════════════════════════════════════╗
# ║  MAIN                                                   ║
# ╚═══════════════════════════════════════════════════════════╝
if __name__ == '__main__':
    t0 = time.time()
    safe_print("=" * 60)
    safe_print("  MIS — Market Intelligence Scanner (Lightweight)")
    safe_print("  Max 50 articles from top-tier sources")
    safe_print("=" * 60)

    # 1. Parse feeds
    safe_print(f"\n[1/5] Parsing {len(FEEDS)} feeds...")
    feed_results = parse_all()
    total_raw = sum(len(v['entries']) for v in feed_results.values())
    safe_print(f"      {total_raw} raw entries from {len(feed_results)}/{len(FEEDS)} feeds")

    # 2. Extract & filter by date
    safe_print("\n[2/5] Filtering & deduplicating...")
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    articles = []
    seen_links = set()

    for source, data in feed_results.items():
        tier = data['tier']
        for entry in data['entries']:
            dt = parse_date(entry)
            if not dt or dt < cutoff: continue

            link = entry.get('link','')
            if not link or link in seen_links: continue
            seen_links.add(link)

            title = clean_html(entry.get('title',''))
            summary = clean_html(entry.get('description',''))
            if not title: continue

            articles.append({
                'source': source, 'tier': tier,
                'title': title, 'summary': summary,
                'link': link, 'date': dt.strftime('%Y-%m-%d %H:%M'),
                'sectors': [], 'etf_tickers': [], 'matched_kw': [],
                'score': 0, 'llm': None,
            })

    safe_print(f"      {len(articles)} articles in last {LOOKBACK_DAYS}d")

    # Fallback
    if len(articles) < 5:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=FALLBACK_DAYS)
        articles = []
        seen_links = set()
        for source, data in feed_results.items():
            for entry in data['entries']:
                dt = parse_date(entry)
                if not dt or dt < cutoff: continue
                link = entry.get('link','')
                if not link or link in seen_links: continue
                seen_links.add(link)
                title = clean_html(entry.get('title',''))
                summary = clean_html(entry.get('description',''))
                if not title: continue
                articles.append({
                    'source': source, 'tier': feed_results[source]['tier'],
                    'title': title, 'summary': summary,
                    'link': link, 'date': dt.strftime('%Y-%m-%d %H:%M'),
                    'sectors': [], 'etf_tickers': [], 'matched_kw': [],
                    'score': 0, 'llm': None,
                })
        safe_print(f"      Fallback {FALLBACK_DAYS}d: {len(articles)} articles")

    if not articles:
        safe_print("\n[!] No articles found. Exiting.")
        # Write empty JSON
        with open(OUTPUT_FILE,'w') as f: json.dump({'generated':datetime.now().isoformat(),'articles':[]},f)
        sys.exit(0)

    # 3. Scrape missing summaries + classify
    safe_print("\n[3/5] Classifying & scoring...")
    for art in articles:
        if len(art['summary']) < 30:
            scraped = scrape_summary(art['link'])
            if scraped: art['summary'] = scraped

        # Keyword classification
        sectors, matched_kw = classify_by_keywords(art['title'], art['summary'])
        art['sectors'] = sectors
        art['matched_kw'] = matched_kw

        # ETF ticker detection
        art['etf_tickers'] = detect_etf_tickers(art['title'] + ' ' + art['summary'])

        # Score
        art['score'] = score_article(art['tier'], sectors, matched_kw,
                                      art['title'], art['summary'], art['etf_tickers'])

    # Sort by score, take top MAX_ARTICLES
    articles.sort(key=lambda a: a['score'], reverse=True)
    articles = articles[:MAX_ARTICLES]
    safe_print(f"      Top {len(articles)} articles selected (score range: {articles[0]['score']:.1f} - {articles[-1]['score']:.1f})")

    # 4. LLM enrichment
    safe_print("\n[4/5] LLM enrichment...")
    articles = llm_enrich(articles)

    # Re-sort after LLM scoring
    articles.sort(key=lambda a: a['score'], reverse=True)

    # 5. Output JSON
    safe_print("\n[5/5] Writing JSON...")

    # Assign each article to its PRIMARY sector (best match) to avoid duplicates
    for art in articles:
        if art['sectors']:
            # Primary = first sector (keyword classification sorts them)
            art['primary_sector'] = art['sectors'][0]
        else:
            art['primary_sector'] = None

        # Fallback sentiment detection if LLM didn't run or returned neutral
        llm_impact = (art.get('llm') or {}).get('impact', '')
        if not llm_impact or llm_impact == 'neutral':
            kw_sent = detect_sentiment(art['title'], art['summary'])
            if art.get('llm') and isinstance(art['llm'], dict):
                if kw_sent != 'neutral':
                    art['llm']['impact'] = kw_sent
            else:
                art['llm'] = {'impact': kw_sent, 'headline_it': '', 'summary_it': '', 'rotation': ''}

    # Build sector summary — each article appears in ONE sector only
    sector_news = {}
    used_links = set()
    for sec in SECTOR_ORDER:
        # Primary assignments first, then secondary
        sec_arts_primary = [a for a in articles if a.get('primary_sector') == sec and a['link'] not in used_links]
        sec_arts_secondary = [a for a in articles if sec in a['sectors'] and a.get('primary_sector') != sec and a['link'] not in used_links]
        sec_arts = sec_arts_primary + sec_arts_secondary
        if sec_arts:
            top_arts = sorted(sec_arts, key=lambda x: x['score'], reverse=True)[:3]
            for a in top_arts:
                used_links.add(a['link'])
            sector_news[sec] = {
                'count': len([a for a in articles if sec in a['sectors']]),
                'top': [{
                    'headline': (a.get('llm') or {}).get('headline_it','') or a['title'],
                    'summary': (a.get('llm') or {}).get('summary_it','') or a['summary'],
                    'impact': (a.get('llm') or {}).get('impact','neutral'),
                    'source': a['source'],
                    'score': a['score'],
                    'link': a['link'],
                    'etf_tickers': a['etf_tickers'][:4],
                } for a in top_arts]
            }

    # Build rotation signals
    rotations = []
    for a in articles:
        rot = (a.get('llm') or {}).get('rotation','')
        if rot and len(rot) > 5:
            rotations.append({'signal': rot, 'source': a['source'], 'score': a['score']})
    rotations = sorted(rotations, key=lambda r: r['score'], reverse=True)[:5]

    output = {
        'generated': datetime.now().isoformat(),
        'lookback_days': LOOKBACK_DAYS,
        'total_articles': len(articles),
        'sector_news': sector_news,
        'rotation_signals': rotations,
        'articles': [{
            'title': a['title'],
            'headline_it': (a.get('llm') or {}).get('headline_it', ''),
            'summary_it': (a.get('llm') or {}).get('summary_it', ''),
            'summary_en': a['summary'],
            'source': a['source'],
            'link': a['link'],
            'date': a['date'],
            'score': a['score'],
            'impact': (a.get('llm') or {}).get('impact', 'neutral'),
            'sectors': a['sectors'],
            'primary_sector': a.get('primary_sector', ''),
            'etf_tickers': a['etf_tickers'],
            'rotation': (a.get('llm') or {}).get('rotation', ''),
        } for a in articles],
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    safe_print(f"      -> {os.path.basename(OUTPUT_FILE)} ({os.path.getsize(OUTPUT_FILE)/1024:.1f} KB)")

    # Print briefing
    safe_print(f"\n{'='*60}")
    safe_print(f"  BRIEFING — {len(articles)} articles")
    safe_print(f"{'='*60}")
    for sec in SECTOR_ORDER:
        if sec in sector_news:
            sn = sector_news[sec]
            top = sn['top'][0] if sn['top'] else None
            impact_sym = {'bullish':'\u25B2','bearish':'\u25BC','mixed':'\u25C6','neutral':'\u25CB'}
            if top:
                imp = impact_sym.get(top['impact'],'\u25CB')
                safe_print(f"  {sec:25s} {sn['count']:2d} news  {imp} {top['headline'][:45]}")
    if rotations:
        safe_print(f"\n  ROTAZIONI:")
        for r in rotations[:3]:
            safe_print(f"    \u21BB {r['signal'][:65]}")

    safe_print(f"\n  Done in {time.time()-t0:.0f}s")
    safe_print(f"{'='*60}")
