# Session Injector

Desktop platform in Python for **managing, validating, analysing and using
authenticated browser sessions** exported as cookies.

> ⚠️ **Authorised use only.** This tool is intended for your **own** accounts
> and sessions — for learning browser automation, building a portfolio, and
> understanding how session restoration works. Do not use it to access
> accounts you do not own or are not authorised to use. Injecting cookies is
> the same mechanism QA/testing frameworks use to restore a logged-in state.

---

## What it does

Given a cookie export from your browser, Session Injector will:

1. **Import** cookies (Netscape `cookies.txt` or JSON exports).
2. **Analyse** their integrity — expiry, attributes, sizes, duplicates,
   broken encoding, structural validity.
3. **Validate** whether the session is likely still usable, in escalating
   levels — from cheap offline checks up to a real browser round-trip.
4. **Inject** the cookies into an automated Chromium context and navigate to
   the service.
5. **Score** the session with a 0–100 **Session Health Score**.

## Architecture

```
        GUI / CLI (ui/, app.py)
              │
        Cookie Manager  ── loader.py
              │
        Cookie Parser   ── parser.py  → models.Cookie
              │
        Cookie Analyzer ── analyzer.py → AnalysisReport
              │
        Session Validator ── browser/validator.py (levels 1-4)
              │
        Browser Manager  ── browser/manager.py
              │
          Playwright ──→ Chromium
              │
        Health Score    ── core/health.py
```

## Project layout

```
SessionInjector/
├── app.py                 # CLI entry point (import → analyse → test → score)
├── config/
│   └── profiles.py        # per-service profiles (domains, required cookies, tests)
├── cookies/
│   ├── models.py          # Cookie + result dataclasses
│   ├── parser.py          # Netscape / JSON parsers
│   ├── loader.py          # format detection, multi-file import
│   └── analyzer.py        # integrity analysis
├── browser/
│   ├── manager.py         # Playwright/Chromium lifecycle
│   ├── injector.py        # context.add_cookies() injection
│   └── validator.py       # layered validation (levels 1-4)
├── core/
│   ├── health.py          # Session Health Score
│   ├── session_tester.py  # multi-service orchestration
│   └── logging_config.py  # console + file logging
├── ui/
│   ├── dashboard.py       # framework-agnostic renderers
│   └── gui.py             # Tkinter desktop window
├── tests/                 # pytest suite (no browser needed)
├── storage/  logs/  profiles/  assets/
└── requirements.txt

run_gui.py                 # root launcher for the GUI (click ▶ in PyCharm)
```

## Install

```bash
pip install -r requirements.txt
# Browser-based validation (levels 2-4) also needs Chromium:
playwright install chromium
```

Parsing, analysis and health scoring work with **zero third-party
dependencies** — Playwright is only imported when a browser test actually runs.

## Usage

### Desktop GUI (easiest)

A Tkinter window — no terminal needed. From the project root:

```bash
python run_gui.py
```

In PyCharm you can just open `run_gui.py` and click the green ▶ button (it uses
an absolute import, so no "run as module" setup is required). Then:

1. Click **📂 Importar cookies…** and pick a `cookies.txt` / `.json` export.
2. The analysis cards (total / valid / expired / …) fill in instantly.
3. **Sessões** tab — each recognised service shows a **Health Score** bar and a
   **🌐 Abrir logado** button that opens a real Chromium window with the cookies
   injected (e.g. Google opens already signed in to your account).
4. **Domínios** tab — every site found in your cookies, searchable, each with a
   **🌐 Abrir** button that opens that site logged in.
5. Tick **Testar no navegador ao importar** to also run the automated headless
   round-trip during import.

The **Abrir** buttons open a visible browser and keep it open until you close
it — so this needs Chromium installed:

```bash
pip install playwright
playwright install chromium
```

Tkinter ships with the standard Python installer, so the GUI itself and all the
local (no-browser) checks need no extra dependency.

### Command line

```bash
# Analyse a cookie export
python -m SessionInjector.app analyze cookies.json

# Full run: import + analyse + validate + browser test + score
python -m SessionInjector.app test cookies.txt

# Local-only (no browser), one service
python -m SessionInjector.app test cookies.json --no-browser --service google

# Inject cookies and open a visible browser
python -m SessionInjector.app open cookies.json --service google
```

Try it against the bundled fake sample (local checks only):

```bash
python -m SessionInjector.app test assets/sample_cookies.example.json --no-browser
```

## The four validation levels

| Level | Name     | Cost    | Check                                              |
|-------|----------|---------|---------------------------------------------------|
| 1     | Local    | offline | Are there any non-expired cookies for the service?|
| 2     | Domain   | offline | Do we actually hold cookies for the target domain?|
| 3     | Required | offline | Are the essential session cookies present?        |
| 4     | Browser  | online  | Inject → navigate → inspect final URL & DOM.      |

Cheaper levels short-circuit: if all cookies are expired or half the required
cookies are missing, the browser is never launched.

## Session Health Score

Rather than a binary works / doesn't-work, the score (0–100) is a weighted,
explainable blend:

| Factor       | Weight | Signal                                             |
|--------------|--------|----------------------------------------------------|
| essential    | 35     | fraction of required session cookies present       |
| freshness    | 20     | fraction of the service's cookies not expired      |
| attributes   | 15     | `Secure` / `HttpOnly` / `SameSite` set as expected |
| consistency  | 10     | cookies concentrated on the target domain          |
| browser      | 20     | real browser test result                           |

When no browser test runs, the browser weight is redistributed so the local
score still tops out at 100. Each factor's point contribution is reported, so
you can see *why* a session scored what it did.

## Why injection sometimes fails

Populating the cookie store isn't a guarantee — the **server** decides whether
to honour the session. Common reasons a valid-looking injection still fails:

- cookies **expired**;
- **incomplete** export (e.g. `SID` present but `SAPISID`/`HSID`/`SSID` missing);
- **wrong domain** for the page you open (`.google.com` vs `mail.google.com`);
- **path** mismatch — the browser only sends cookies whose `path` matches;
- `Secure` cookies only sent over HTTPS;
- **inconsistent** cookies (some new, some stale);
- state kept **outside cookies** (local storage, device/context binding), or
  the service re-verifying identity when the context changes.

The analyzer and health score surface most of these before you ever open a
browser.

## Tests

```bash
pytest SessionInjector/tests -q
```

The test suite covers parsing, analysis, layered validation and the health
score, and runs **without** a browser.

## Roadmap

- [x] Desktop GUI (Tkinter) over the same `core` API — `run_gui.py`
- [ ] Drag-and-drop file import in the GUI
- [ ] Persist imported sets to `storage/` with an audit trail
- [ ] More service profiles
- [ ] Export health reports to JSON/HTML
```
