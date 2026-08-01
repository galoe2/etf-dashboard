"""
make_watchlist.py — Aggiorna i dati della watchlist del blog Ex Ante.

La composizione si definisce in watchlist.json (root del repo, rivista ogni mese);
questo script scarica prezzi e performance reali via yfinance e scrive
<SITE_DIR>/src/data/watchlist.json per la pagina /watchlist/ del sito.

Metriche per titolo: prezzo, valuta, MTD (da fine mese precedente), YTD,
3 mesi, distanza dal massimo a 52 settimane.
"""

import os, json, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ETF_Dashboard/
CONFIG = os.path.join(ROOT, "watchlist.json")


def _default_site_dir():
    parent = os.path.dirname(ROOT)
    candidates = [
        os.path.join(parent, "exante"),
        os.path.join(parent, "Blog", "exante"),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "src")):
            return c
    return candidates[0]


SITE_DIR = os.environ.get("SITE_DIR", _default_site_dir())
TODAY = datetime.now().strftime("%Y-%m-%d")


def pct(last, base):
    if base is None or last is None or base == 0:
        return None
    return round((last / base - 1) * 100, 2)


def main():
    import yfinance as yf

    if not os.path.exists(CONFIG):
        print(f"  ERRORE: {CONFIG} non trovato")
        sys.exit(1)
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    now = datetime.now()
    items = []
    for entry in cfg.get("items", []):
        tk = entry["ticker"]
        try:
            t = yf.Ticker(tk)
            hist = t.history(period="1y", auto_adjust=True)
            closes = hist["Close"].dropna()
            if len(closes) < 5:
                print(f"  {tk}: dati insufficienti, salto")
                continue
            last = float(closes.iloc[-1])
            # baseline MTD: ultima chiusura del mese precedente
            prev_month = closes[closes.index.strftime("%Y-%m") < now.strftime("%Y-%m")]
            mtd_base = float(prev_month.iloc[-1]) if len(prev_month) else None
            # baseline YTD: ultima chiusura dell'anno precedente
            prev_year = closes[closes.index.strftime("%Y") < now.strftime("%Y")]
            ytd_base = float(prev_year.iloc[-1]) if len(prev_year) else None
            m3_base = float(closes.iloc[-64]) if len(closes) >= 64 else None
            hi_52w = float(closes.max())

            info = {}
            try:
                info = t.info or {}
            except Exception:
                pass
            name = entry.get("name") or info.get("longName") or info.get("shortName") or tk
            currency = info.get("currency") or ""

            items.append({
                "ticker": tk.split(".")[0],
                "yf_ticker": tk,
                "name": name,
                "type": entry.get("type", "stock"),
                "note": entry.get("note", ""),
                "price": round(last, 2),
                "currency": currency,
                "mtd": pct(last, mtd_base),
                "ytd": pct(last, ytd_base),
                "m3": pct(last, m3_base),
                "from_high": pct(last, hi_52w),
            })
            print(f"  {tk}: OK ({name[:40]})")
        except Exception as e:
            print(f"  {tk}: ERRORE ({e})")

    if not items:
        print("  ERRORE: nessun dato scaricato")
        sys.exit(1)

    out_dir = os.path.join(SITE_DIR, "src", "data")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "watchlist.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "month": cfg.get("month", now.strftime("%Y-%m")),
            "updated": TODAY,
            "items": items,
        }, f, ensure_ascii=False, indent=2)
    print(f"  Watchlist -> {out} ({len(items)} titoli)")


if __name__ == "__main__":
    main()
