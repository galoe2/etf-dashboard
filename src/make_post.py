"""
make_post.py — Genera l'articolo settimanale del blog Ex Ante (rubrica MERCATI)
a partire dai dati della pipeline ETF (data/analysis_YYYY-Www.json).

Output:
  <SITE_DIR>/src/content/blog/mercati-settimana-YYYY-Www.md
  <SITE_DIR>/public/reports/ETF_Report_YYYY-Www.html   (copia del report completo)

Config:
  SITE_DIR      — path del sito Astro (default: ../../exante rispetto a questo file)
  GROQ_API_KEY  — se presente, titolo/abstract/corpo sono scritti dall'AI;
                  altrimenti viene usato un template deterministico sui dati.
"""

import os, re, json, shutil, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ETF_Dashboard/
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")
SITE_DIR = os.environ.get("SITE_DIR", os.path.join(os.path.dirname(ROOT), "exante"))

WEEK = datetime.now().strftime("%Y-W%V")
TODAY = datetime.now().strftime("%Y-%m-%d")


def find_latest(folder, prefix, suffix):
    if not os.path.isdir(folder):
        return None
    files = sorted(f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(suffix))
    return os.path.join(folder, files[-1]) if files else None


def load_analysis():
    # Preferisce il file appena generato in src/, poi il più recente in data/
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_data.json")
    path = local if os.path.exists(local) else find_latest(DATA, "analysis_", ".json")
    if not path:
        print("  ERRORE: nessun analysis_*.json trovato. Esegui prima build_report.py")
        sys.exit(1)
    print(f"  Dati: {os.path.basename(path)}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def fmt_pct(v):
    return f"{v:+.1f}%".replace(".", ",")


def market_regime(mo):
    """Regime deterministico da SPY 1W + breadth: RISK-ON / RISK-OFF / ROTATIONAL."""
    spy = mo.get("spy_1w", 0)
    try:
        pos, tot = mo.get("breadth", "0/1").split("/")
        ratio = int(pos) / max(int(tot), 1)
    except Exception:
        ratio = 0.5
    if spy > 0.5 and ratio >= 0.6:
        return "RISK-ON"
    if spy < -0.5 and ratio <= 0.4:
        return "RISK-OFF"
    return "ROTATIONAL"


def sparkline_points(values, width=64, height=18, pad=2):
    """Serie numerica -> stringa punti per la polyline SVG delle card (64x18)."""
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * (width - 2 * pad) / (len(vals) - 1)
        y = height - pad - (v - lo) * (height - 2 * pad) / span
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


# ── Corpo articolo: AI (Groq) con fallback deterministico ──────────

def ai_article(analysis, commentary_text):
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=key)
        prompt = f"""Sei l'autore del blog finanziario italiano "Ex Ante" (tagline: "Prima che accada. Mercati, modelli, dati.").
Scrivi l'articolo settimanale della rubrica MERCATI a partire dai dati quantitativi e dal commento tecnico forniti.

Stile: prima persona, sobrio, analitico, zero sensazionalismo. Tesi sempre condizionali ("se... allora"), mai certezze.
Struttura del corpo (markdown):
- 1 paragrafo introduttivo senza titolo
- "## Cosa dicono i dati" — regime di mercato, breadth, settori/regioni migliori e peggiori con i numeri
- "## Rotazioni e flussi" — dove entra e da dove esce il capitale, RSI estremi
- "## La lettura ex ante" — la tesi della settimana come struttura di condizioni; includi una citazione in blockquote (una frase memorabile)
- "## Cosa guardo da qui" — elenco puntato di 3 segnali verificabili per la settimana successiva
400-550 parole totali. Numeri con virgola decimale (stile italiano).

Rispondi SOLO con un JSON valido, senza backtick:
{{"title": "titolo dell'articolo (max 80 caratteri, niente due punti iniziali tipo 'Mercati:')", "abstract": "abstract di 1-2 frasi (max 160 caratteri)", "body": "corpo in markdown", "table_comment": "commento di 1-2 frasi (max 240 caratteri) al Market Pulse per la home: cosa guida, cosa resta indietro, eccessi da monitorare"}}

DATI QUANTITATIVI:
{json.dumps(analysis, ensure_ascii=False)}

COMMENTO TECNICO DELLA PIPELINE (da riscrivere, non copiare):
{commentary_text[:4000]}"""
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2500,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(json)?\s*|```$", "", raw).strip()
        data = json.loads(raw)
        if data.get("title") and data.get("body"):
            print("  Articolo AI: OK")
            return data
    except Exception as e:
        print(f"  Articolo AI: fallback deterministico ({e})")
    return None


def deterministic_article(analysis):
    mo = analysis.get("market_overview", {})
    bs, ws = mo.get("best_sector", {}), mo.get("worst_sector", {})
    br = analysis.get("best_region", {})
    wr = analysis.get("worst_region", {})
    flows = analysis.get("capital_flows", {})
    inflow = ", ".join(f["group"] for f in flows.get("inflow", [])[:3]) or "n.d."
    outflow = ", ".join(f["group"] for f in flows.get("outflow", [])[:3]) or "n.d."
    rsi = analysis.get("rsi_extremes", {})
    ob = ", ".join(x["t"] for x in rsi.get("overbought", [])) or "nessuno"
    os_ = ", ".join(x["t"] for x in rsi.get("oversold", [])) or "nessuno"

    title = f"La settimana dei mercati: {bs.get('name','–')} guida, {ws.get('name','–')} in coda"
    abstract = (
        f"SPY {fmt_pct(mo.get('spy_1w', 0))} sulla settimana. "
        f"Capitale in ingresso su {inflow.split(',')[0] if inflow != 'n.d.' else '–'}: la lettura settimanale dei dati su oltre 100 ETF."
    )
    body = f"""Come ogni settimana, la pipeline ha passato in rassegna oltre 100 ETF tra settori e regioni. Qui sotto la sintesi dei numeri; il dettaglio completo, con tabelle e grafici interattivi, è nel report allegato in fondo.

## Cosa dicono i dati

SPY ha chiuso la settimana a {fmt_pct(mo.get('spy_1w', 0))}, QQQ a {fmt_pct(mo.get('qqq_1w', 0))}, con una breadth settoriale di {mo.get('breadth', 'n.d.')} settori positivi. Il settore migliore è stato {bs.get('name','–')} ({fmt_pct(bs.get('w1', 0))}), il peggiore {ws.get('name','–')} ({fmt_pct(ws.get('w1', 0))}). Tra le regioni, {br.get('name','–')} ({fmt_pct(br.get('w1', 0))}) contro {wr.get('name','–')} ({fmt_pct(wr.get('w1', 0))}).

## Rotazioni e flussi

I proxy dei flussi indicano capitale in ingresso su {inflow} e in uscita da {outflow}. Sul fronte degli eccessi: RSI in ipercomprato per {ob}, in ipervenduto per {os_}.

## La lettura ex ante

> I numeri di una settimana non fanno una tesi: fanno una lista di condizioni da verificare la settimana dopo.

Se i flussi confermano la rotazione e la breadth non si deteriora, la struttura resta costruttiva; in caso contrario, la settimana andrà archiviata come rumore.

## Cosa guardo da qui

- La conferma (o smentita) dei flussi su {inflow.split(',')[0] if inflow != 'n.d.' else 'settori in accumulo'}.
- Il rientro degli RSI estremi senza danni sui prezzi.
- La tenuta della breadth settoriale sopra la metà dei settori."""
    return {"title": title, "abstract": abstract, "body": body}


def write_market_json(analysis, article, week, counts=None, spy_weekly=None, report_ref=""):
    """Aggiorna src/data/market.json del sito: Market Pulse + overview + commento per la home."""
    mo = analysis.get("market_overview", {})
    comment = article.get("table_comment", "")
    if not comment:
        bs, ws = mo.get("best_sector", {}), mo.get("worst_sector", {})
        flows = analysis.get("capital_flows", {})
        inflow = ", ".join(f["group"] for f in flows.get("inflow", [])[:2])
        comment = (
            f"Settimana a {fmt_pct(mo.get('spy_1w', 0))} per SPY, breadth {mo.get('breadth', 'n.d.')}: "
            f"guida {bs.get('name', '–')} ({fmt_pct(bs.get('w1', 0))}), in coda {ws.get('name', '–')} "
            f"({fmt_pct(ws.get('w1', 0))})."
        )
        if inflow:
            comment += f" Flussi in ingresso su {inflow}."
    risk = analysis.get("risk", {})
    rsi = analysis.get("rsi_extremes", {})
    data_dir = os.path.join(SITE_DIR, "src", "data")
    os.makedirs(data_dir, exist_ok=True)
    out = os.path.join(data_dir, "market.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "week": week,
            "updated": TODAY,
            "comment": comment,
            "overview": {
                "spy_1w": mo.get("spy_1w", 0),
                "qqq_1w": mo.get("qqq_1w", 0),
                "breadth": mo.get("breadth", ""),
                "realized_vol": risk.get("realized_vol", None),
                "risk_score": risk.get("risk_score", None),
            },
            "gainers": analysis.get("top_gainers", [])[:5],
            "losers": analysis.get("top_losers", [])[:5],
            "overbought": rsi.get("overbought", [])[:5],
            "oversold": rsi.get("oversold", [])[:5],
            "pipeline": {
                "week": week,
                "etfs": (counts or {}).get("etfs"),
                "sectors": (counts or {}).get("sectors"),
                "regions": (counts or {}).get("regions"),
                "regime": market_regime(mo),
                "risk_score": risk.get("risk_score"),
                "report": report_ref,
            },
            "spy_spark": sparkline_points(spy_weekly or []),
        }, f, ensure_ascii=False, indent=2)
    print(f"  Market pulse -> {out}")


def main():
    print(f"  Sito: {SITE_DIR}")
    payload = load_analysis()
    analysis = payload.get("analysis", payload)
    week = payload.get("week", WEEK)
    commentary = strip_html(payload.get("ai_commentary_html", ""))

    article = ai_article(analysis, commentary) or deterministic_article(analysis)

    # Copia il report HTML completo in public/reports/
    report_src = find_latest(OUT, "ETF_Report_", ".html")
    report_ref = ""
    if report_src:
        reports_dir = os.path.join(SITE_DIR, "public", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        dst = os.path.join(reports_dir, os.path.basename(report_src))
        shutil.copy2(report_src, dst)
        report_ref = f"/reports/{os.path.basename(report_src)}"
        print(f"  Report copiato: {report_ref}")

    write_market_json(
        analysis, article, week,
        counts=payload.get("counts"),
        spy_weekly=payload.get("spy_weekly"),
        report_ref=report_ref,
    )

    spy = analysis.get("market_overview", {}).get("spy_1w", 0)
    stat = f"SPY {fmt_pct(spy)}"
    spark = sparkline_points(payload.get("spy_weekly") or [])

    fm = [
        "---",
        f'title: "{article["title"].replace(chr(34), chr(92) + chr(34))}"',
        "rubrica: MERCATI",
        f"date: {TODAY}",
        f'abstract: "{article.get("abstract", "").replace(chr(34), chr(92) + chr(34))}"',
        f'stat: "{stat}"',
    ]
    if spark:
        fm.append(f'sparkline: "{spark}"')
    if report_ref:
        fm.append(f'report: "{report_ref}"')
    fm.append("---")
    md = "\n".join(fm) + "\n\n" + article["body"] + "\n"

    posts_dir = os.path.join(SITE_DIR, "src", "content", "blog")
    os.makedirs(posts_dir, exist_ok=True)
    out_path = os.path.join(posts_dir, f"mercati-settimana-{week.lower()}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  Articolo -> {out_path}")


if __name__ == "__main__":
    main()
