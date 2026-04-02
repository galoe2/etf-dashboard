"""
ETF Market Intelligence Dashboard — Weekly Launcher

  Step 1: scan_news.py    → data/news_YYYY-Www.json
  Step 2: build_report.py → output/ETF_Report_YYYY-Www.html
  Step 3: (opzionale) invia report via email

Uso:
    python run.py                  # genera report
    python run.py --skip-news      # salta news, usa dati esistenti
    python run.py --news-only      # solo scanner news
    python run.py --email           # genera + invia email
    python run.py --email-only     # invia ultimo report senza rigenerare

Configurazione email (variabili d'ambiente o config.json):
    EMAIL_TO       = indirizzo destinatario
    EMAIL_FROM     = indirizzo Gmail mittente
    EMAIL_PASSWORD = App Password Gmail (NON la password normale)
"""

import subprocess, sys, os, shutil, time, argparse, json
from datetime import datetime

# ═══════════════════════════════════════════════════════════
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "src")
DATA = os.path.join(ROOT, "data")
OUT  = os.path.join(ROOT, "output")
PY   = sys.executable

NOW   = datetime.now()
WEEK  = NOW.strftime("%Y-W%V")
TODAY = NOW.strftime("%Y-%m-%d")

for d in [SRC, DATA, OUT]:
    os.makedirs(d, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# CONFIG — da config.json o variabili d'ambiente
# ═══════════════════════════════════════════════════════════
CFG_PATH = os.path.join(ROOT, "config.json")
CFG = {}
if os.path.exists(CFG_PATH):
    with open(CFG_PATH, 'r') as f:
        CFG = json.load(f)

def cfg(key, default=""):
    return os.environ.get(key, CFG.get(key, default))


# ═══════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════
def banner(text):
    print(f"\n{'=' * 58}\n  {text}\n{'=' * 58}")

def run(script):
    path = os.path.join(SRC, script)
    if not os.path.exists(path):
        print(f"  ERRORE: {script} non trovato"); return False
    print(f"  -> {script}")
    t0 = time.time()
    # Pass config values as env vars so scripts can read them
    env = os.environ.copy()
    for key in ["GROQ_API_KEY", "RESEND_API_KEY", "EMAIL_TO", "EMAIL_FROM", "EMAIL_PASSWORD"]:
        val = cfg(key)
        if val: env[key] = val
    proc = subprocess.run([PY, path], cwd=SRC, timeout=600, env=env)
    dt = time.time() - t0
    ok = proc.returncode == 0
    print(f"  {'OK' if ok else 'ERRORE'} ({dt:.0f}s)")
    return ok

def move(src_name, dst_name):
    src = os.path.join(SRC, src_name)
    if not os.path.exists(src): return None
    name, ext = os.path.splitext(dst_name)
    dated = os.path.join(OUT, f"{name}_{WEEK}{ext}")
    shutil.move(src, dated)
    sz = os.path.getsize(dated)
    h = f"{sz/1024:.0f}K" if sz < 1048576 else f"{sz/1048576:.1f}M"
    print(f"  -> output/{name}_{WEEK}{ext}  ({h})")
    return dated

def install_deps():
    req = os.path.join(ROOT, "requirements.txt")
    if os.path.exists(req):
        subprocess.run([PY, "-m", "pip", "install", "-q", "-r", req], capture_output=True)
    else:
        subprocess.run([PY, "-m", "pip", "install", "-q",
            "numpy", "pandas", "yfinance", "feedparser",
            "requests", "beautifulsoup4", "groq"], capture_output=True)
    print("  OK")

def find_latest_report():
    """Find most recent ETF_Report in output/."""
    reports = sorted([f for f in os.listdir(OUT) if f.startswith("ETF_Report_") and f.endswith(".html")], reverse=True)
    return os.path.join(OUT, reports[0]) if reports else None

def find_latest_news():
    """Find most recent news file in data/."""
    news = sorted([f for f in os.listdir(DATA) if f.startswith("news_") and f.endswith(".json")], reverse=True)
    return os.path.join(DATA, news[0]) if news else None


# ═══════════════════════════════════════════════════════════
# EMAIL via Resend API (solo API key, no password)
# ═══════════════════════════════════════════════════════════
def send_email(report_path):
    """Send report via Resend API or Gmail SMTP fallback."""
    import base64

    email_to = cfg("EMAIL_TO")
    resend_key = cfg("RESEND_API_KEY")

    # ── Resend (preferito: solo API key) ──────────────
    if resend_key and email_to:
        try:
            import requests as req_lib
            filename = os.path.basename(report_path)
            filesize = os.path.getsize(report_path)
            print(f"  Invio via Resend a {email_to}...")
            print(f"  File: {filename} ({filesize/1024:.0f} KB)")

            with open(report_path, 'rb') as f:
                content_b64 = base64.b64encode(f.read()).decode()

            resp = req_lib.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "ETF Dashboard <onboarding@resend.dev>",
                    "to": [email_to],
                    "subject": f"ETF Report {WEEK}",
                    "html": f"<h2>ETF Market Intelligence Report — {WEEK}</h2><p>Generato il {TODAY}.</p><p>109 ETF | 13 settori | 8 regioni | AI commentary</p><p><strong>Report HTML in allegato</strong> — aprire nel browser.</p>",
                    "attachments": [{
                        "filename": filename,
                        "content": content_b64,
                    }]
                },
                timeout=30,
            )
            print(f"  Resend response: {resp.status_code} — {resp.text[:200]}")
            if resp.status_code in (200, 201):
                print(f"  OK — inviato a {email_to} (via Resend)")
                print(f"  Controlla inbox + cartella SPAM")
                return True
            else:
                print(f"  ERRORE Resend: {resp.status_code}")
                if "can only send" in resp.text.lower() or "verify" in resp.text.lower():
                    print(f"  >>> Verifica {email_to} su resend.com")
        except Exception as e:
            print(f"  ERRORE Resend: {e}")

    # ── Gmail SMTP (fallback: richiede App Password) ──
    email_from = cfg("EMAIL_FROM")
    email_pass = cfg("EMAIL_PASSWORD")

    if email_from and email_pass and email_to:
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            filename = os.path.basename(report_path)
            msg = MIMEMultipart()
            msg['From'] = email_from
            msg['To'] = email_to
            msg['Subject'] = f"ETF Report {WEEK}"
            msg.attach(MIMEText(f"ETF Report {WEEK}\nGenerato il {TODAY}.\nReport in allegato.", 'plain'))

            with open(report_path, 'rb') as f:
                part = MIMEBase('text', 'html')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(email_from, email_pass)
            server.send_message(msg)
            server.quit()
            print(f"  OK — inviato a {email_to} (via Gmail)")
            return True
        except Exception as e:
            print(f"  ERRORE Gmail: {e}")

    if not email_to:
        print("  ERRORE: EMAIL_TO mancante in config.json")
    elif not resend_key and not email_pass:
        print("  ERRORE: serve RESEND_API_KEY oppure EMAIL_FROM + EMAIL_PASSWORD")
    return False


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="ETF Dashboard — Weekly Launcher")
    ap.add_argument("--skip-news", action="store_true", help="Salta scanner news")
    ap.add_argument("--news-only", action="store_true", help="Solo scanner news")
    ap.add_argument("--email", action="store_true", help="Invia report via email dopo generazione")
    ap.add_argument("--email-only", action="store_true", help="Invia ultimo report senza rigenerare")
    ap.add_argument("--test-email", action="store_true", help="Test invio email con file di prova")
    args = ap.parse_args()

    report_path = None

    # ── Test email: quick test without report ────────
    if args.test_email:
        banner("Test Email")
        test_file = os.path.join(OUT, "_test_email.html")
        with open(test_file, 'w') as f:
            f.write(f"<html><body><h1>ETF Dashboard — Test Email</h1><p>Se leggi questo, l'email funziona!</p><p>{TODAY}</p></body></html>")
        print(f"  Config: EMAIL_TO={cfg('EMAIL_TO')}")
        print(f"  Config: RESEND_API_KEY={'***' + cfg('RESEND_API_KEY')[-6:] if cfg('RESEND_API_KEY') else 'MANCANTE'}")
        send_email(test_file)
        os.remove(test_file)
        return

    # ── Email-only: skip generation ────────────────────
    if args.email_only:
        banner("Invio Email")
        report_path = find_latest_report()
        if report_path:
            print(f"  Report: {os.path.basename(report_path)}")
            send_email(report_path)
        else:
            print("  Nessun report trovato in output/")
        return

    # ── Normal flow ────────────────────────────────────
    banner("ETF Market Intelligence Dashboard")
    print(f"  {TODAY}  (week {WEEK})")

    print("\n  Dipendenze...", end=" ")
    install_deps()

    results = {}

    # ── STEP 1: News Scanner ───────────────────────────
    if not args.skip_news:
        banner("STEP 1/2 — News Scanner (ultimi 7 giorni)")
        ok = run("scan_news.py")
        results["News"] = ok
        nj = os.path.join(SRC, "news_data.json")
        if os.path.exists(nj):
            shutil.move(nj, os.path.join(DATA, f"news_{WEEK}.json"))
    else:
        print("\n  News: skipped (--skip-news)")

    if args.news_only:
        _summary(results, None); return

    # ── STEP 2: Build Report ───────────────────────────
    step_label = "STEP 2/2" if not args.skip_news else "STEP 1/1"
    banner(f"{step_label} — Build Report")
    nd = find_latest_news()
    if nd:
        shutil.copy2(nd, os.path.join(SRC, "news_data.json"))
        print(f"  News data: {os.path.basename(nd)}")
    ok = run("build_report.py")
    results["Report"] = ok
    report_path = move("ETF_Report.html", "ETF_Report.html")

    # ── STEP 3: Email ──────────────────────────────────
    if args.email and report_path:
        banner("STEP 3 — Invio Email")
        ok = send_email(report_path)
        results["Email"] = ok

    _summary(results, report_path)


def _summary(results, report_path):
    banner("DONE")
    for name, ok in results.items():
        print(f"  {'OK' if ok else 'X '}  {name}")

    htmls = sorted(f for f in os.listdir(OUT) if f.endswith(".html"))
    if htmls:
        print(f"\n  Report in output/:")
        for f in htmls:
            sz = os.path.getsize(os.path.join(OUT, f))
            h = f"{sz/1024:.0f}K" if sz < 1048576 else f"{sz/1048576:.1f}M"
            print(f"    {f:40s} {h}")
    if report_path and os.path.exists(report_path):
        print(f"\n  Apri: file://{os.path.abspath(report_path)}")
    print()


if __name__ == "__main__":
    main()
