# ETF Market Intelligence Dashboard

Report settimanale automatizzato: 109 ETF, 12 settori, 8 regioni, news 7gg, AI commentary.

## Quick Start (locale)

```bash
pip install -r requirements.txt
python run.py               # genera report
python run.py --email       # genera + invia email
python run.py --skip-news   # salta news
python run.py --email-only  # invia ultimo report
```

Output: `output/ETF_Report_2025-W10.html`

## Struttura

```
ETF_Dashboard/
├── run.py                         ← Launcher
├── config.json                    ← Chiavi API e email
├── requirements.txt
├── .github/workflows/
│   └── weekly_report.yml          ← Automazione GitHub Actions
├── src/
│   ├── scan_news.py               ← Step 1: RSS 7gg + Groq
│   └── build_report.py            ← Step 2: yfinance + Groq → HTML
├── data/                          ← news_YYYY-Www.json
└── output/                        ← ETF_Report_YYYY-Www.html
```

## Automazione Cloud (GitHub Actions) — GRATIS

Il report si genera automaticamente ogni sabato alle 09:00 CET nel cloud di GitHub, senza PC acceso. Il report viene salvato nel repo e inviato via email.

### Setup (una volta sola)

1. **Crea un repo GitHub** privato e pusha il progetto:
   ```bash
   cd ETF_Dashboard
   git init
   git add .
   git commit -m "initial"
   git remote add origin https://github.com/TUO_USER/etf-dashboard.git
   git push -u origin main
   ```

2. **Aggiungi i Secrets** su GitHub:
   - Vai su repo → Settings → Secrets and variables → Actions → New repository secret
   - Aggiungi:
     - `GROQ_API_KEY` → la tua chiave Groq
     - `EMAIL_TO` → il tuo indirizzo email (dove ricevere il report)
     - `RESEND_API_KEY` → chiave API da resend.com (no password Gmail)

3. **Fatto.** Ogni sabato alle 09:00 il workflow:
   - Installa Python + dipendenze
   - Scansiona le news degli ultimi 7 giorni
   - Scarica dati ETF da yfinance
   - Genera AI commentary via Groq
   - Invia il report HTML via email
   - Salva il report nel repo (storico)

4. **Test manuale**: vai su Actions → "ETF Weekly Report" → Run workflow

### Costi

Zero. GitHub Free include 2.000 minuti/mese. Il report usa ~5 minuti a settimana = ~20 min/mese (1%).

## Email

**Opzione 1 — Resend (consigliata, no password):**
1. Registrati su [resend.com](https://resend.com/signup) con Google/GitHub
2. Dashboard → API Keys → Create
3. Copia la chiave `re_xxxxx` nel secret `RESEND_API_KEY`

Le email arrivano da `onboarding@resend.dev` — controlla lo spam la prima volta.

**Opzione 2 — Gmail SMTP (richiede App Password):**
1. https://myaccount.google.com/apppasswords
2. Genera password per "Mail"
3. Configura `EMAIL_FROM` e `EMAIL_PASSWORD`

## Alternative automazione locale

Se preferisci far girare il report sul tuo PC:

**Windows Task Scheduler:**
```
schtasks /create /tn "ETF Report" /tr "python C:\path\to\run.py --email" /sc weekly /d SAT /st 09:00
```

**Mac/Linux cron:**
```
0 9 * * 6 cd /path/to/ETF_Dashboard && python3 run.py --email >> log.txt 2>&1
```
