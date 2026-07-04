"""Desktop GUI (Tkinter).

A single-window front-end over the same ``core`` API used by the CLI. Tkinter
ships with Python, so this needs no extra install. Long-running work (analysis
and browser tests) runs on a background thread so the window never freezes, and
log records are streamed into the on-screen log panel.

Two tabs:
  * Sessões  — recognised services (Google, YouTube, GitHub) with a Health
    Score and an "Abrir" button that opens a real, logged-in browser.
  * Domínios — every site found in the cookies, searchable, each openable.

Run it with the root launcher:  python run_gui.py
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from ..browser.manager import BrowserUnavailable, open_session, playwright_available
from ..config.profiles import ServiceProfile, profile_for_domain
from ..cookies.analyzer import analyze
from ..cookies.loader import load_files
from ..cookies.models import Cookie, Severity
from ..core.domains import DomainGroup, cookies_for_site, group_by_site
from ..core.logging_config import setup_logging
from ..core.session_tester import test_sessions

# Colours (dark, easy on the eyes).
BG = "#1e1f26"
CARD = "#2a2c36"
FG = "#e6e6e6"
MUTED = "#9aa0b4"
ACCENT = "#5b8def"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"

MAX_DOMAIN_ROWS = 250  # cap rendered rows; the search box reaches the rest


def _score_color(score: int) -> str:
    if score >= 85:
        return GREEN
    if score >= 60:
        return ACCENT
    if score >= 35:
        return YELLOW
    return RED


class QueueLogHandler(logging.Handler):
    """A logging handler that pushes records onto a thread-safe queue."""

    def __init__(self, q: "queue.Queue[str]"):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(self.format(record))


class SessionInjectorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cookies: list[Cookie] = []
        self.groups: list[DomainGroup] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.result_queue: "queue.Queue" = queue.Queue()

        root.title("Session Injector")
        root.geometry("980x680")
        root.minsize(820, 560)
        root.configure(bg=BG)

        self._setup_logging()
        self._build_style()
        self._build_header()
        self._build_body()
        self._build_log()
        self._poll_queues()

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    def _setup_logging(self) -> None:
        logger = setup_logging()
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        self.logger = logger

    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#4a7be0")])
        style.configure("Open.TButton", foreground="white", background=GREEN,
                        font=("Segoe UI", 9, "bold"), padding=4)
        style.map("Open.TButton", background=[("active", "#33a344")])
        style.configure("TCheckbutton", background=BG, foreground=FG,
                        font=("Segoe UI", 10))
        style.configure("Horizontal.TProgressbar", troughcolor=CARD,
                        background=ACCENT, thickness=14)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"),
                        padding=(14, 6))
        style.configure("Search.TEntry", fieldbackground=CARD, foreground=FG)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(header, text="🍪  Session Injector", bg=BG, fg=FG,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(header, text="Uso autorizado — apenas com suas próprias contas",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right", pady=(8, 0))

        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 8))

        self.import_btn = ttk.Button(
            bar, text="📂  Importar cookies…", style="Accent.TButton",
            command=self.on_import,
        )
        self.import_btn.pack(side="left")

        self.browser_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="Testar no navegador ao importar", variable=self.browser_var,
        ).pack(side="left", padx=12)

        self.file_label = tk.Label(bar, text="Nenhum arquivo carregado",
                                   bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.file_label.pack(side="right")

    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        # Left: analysis summary cards.
        left = tk.Frame(body, bg=BG, width=230)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)
        tk.Label(left, text="ANÁLISE", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))
        self.stat_labels: dict[str, tk.Label] = {}
        for key, title in [
            ("total", "Total"), ("valid", "Válidos"), ("expired", "Expirados"),
            ("invalid", "Inválidos"), ("duplicates", "Duplicados"),
            ("domains", "Domínios"),
        ]:
            self.stat_labels[key] = self._stat_card(left, title)

        # Right: tabs (Sessões / Domínios).
        self.notebook = ttk.Notebook(body)
        self.notebook.pack(side="left", fill="both", expand=True)

        sessions_tab = tk.Frame(self.notebook, bg=BG)
        domains_tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(sessions_tab, text="Sessões")
        self.notebook.add(domains_tab, text="Domínios")
        self.sessions_frame = self._make_scrollable(sessions_tab)
        self._build_domains_tab(domains_tab)
        self._placeholder()

    def _stat_card(self, parent, title: str) -> tk.Label:
        card = tk.Frame(parent, bg=CARD)
        card.pack(fill="x", pady=3)
        tk.Label(card, text=title, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=10, pady=6)
        value = tk.Label(card, text="—", bg=CARD, fg=FG,
                         font=("Segoe UI", 13, "bold"))
        value.pack(side="right", padx=10)
        return value

    def _make_scrollable(self, parent) -> tk.Frame:
        """Return an inner frame that scrolls vertically inside ``parent``."""
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)
        return inner

    def _build_domains_tab(self, parent) -> None:
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=4, pady=(4, 6))
        tk.Label(top, text="Buscar:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._render_domains())
        entry = ttk.Entry(top, textvariable=self.search_var, style="Search.TEntry")
        entry.pack(side="left", fill="x", expand=True, padx=8)
        self.domains_count = tk.Label(top, text="", bg=BG, fg=MUTED,
                                      font=("Segoe UI", 9))
        self.domains_count.pack(side="right")
        self.domains_frame = self._make_scrollable(parent)

    def _build_log(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(frame, text="LOGS", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.log_text = tk.Text(frame, height=6, bg="#15161c", fg="#c8ccda",
                                font=("Consolas", 9), relief="flat", wrap="word")
        self.log_text.pack(fill="x", pady=(4, 0))
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Sessions panel
    # ------------------------------------------------------------------ #
    def _clear(self, frame) -> None:
        for w in frame.winfo_children():
            w.destroy()

    def _placeholder(self) -> None:
        tk.Label(
            self.sessions_frame,
            text="Importe um arquivo de cookies para começar.\n\n"
                 "Formatos aceitos: Netscape (cookies.txt) e JSON.",
            bg=BG, fg=MUTED, font=("Segoe UI", 10), justify="left",
        ).pack(anchor="w", pady=20, padx=6)

    def _add_session_card(self, outcome) -> None:
        h = outcome.health
        v = outcome.validation
        color = _score_color(h.score)
        profile = outcome.profile

        card = tk.Frame(self.sessions_frame, bg=CARD)
        card.pack(fill="x", pady=5, padx=4)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(top, text=profile.label, bg=CARD, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(top, text=f"{h.stars}  {h.score}/100", bg=CARD, fg=color,
                 font=("Segoe UI", 12, "bold")).pack(side="right")

        bar = ttk.Progressbar(card, maximum=100, value=h.score,
                              style="Horizontal.TProgressbar")
        bar.pack(fill="x", padx=12, pady=(0, 6))

        bottom = tk.Frame(card, bg=CARD)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        info = f"Status: {v.status.value}  •  {h.grade}"
        if v.missing_required:
            info += f"  •  faltando: {', '.join(v.missing_required)}"
        tk.Label(bottom, text=info, bg=CARD, fg=MUTED, font=("Segoe UI", 9),
                 justify="left", wraplength=460).pack(side="left")
        ttk.Button(bottom, text="🌐 Abrir logado", style="Open.TButton",
                   command=lambda p=profile: self.open_service(p)).pack(side="right")

    # ------------------------------------------------------------------ #
    # Domains panel
    # ------------------------------------------------------------------ #
    def _render_domains(self) -> None:
        self._clear(self.domains_frame)
        term = self.search_var.get().strip().lower()
        matches = [g for g in self.groups if term in g.site] if term else self.groups

        self.domains_count.config(
            text=f"{len(matches)} de {len(self.groups)} sites")

        if not self.groups:
            tk.Label(self.domains_frame, text="Nenhum domínio ainda.", bg=BG,
                     fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=6, pady=10)
            return

        for group in matches[:MAX_DOMAIN_ROWS]:
            self._add_domain_row(group)
        if len(matches) > MAX_DOMAIN_ROWS:
            tk.Label(
                self.domains_frame,
                text=f"… e mais {len(matches) - MAX_DOMAIN_ROWS}. "
                     f"Refine a busca para ver o resto.",
                bg=BG, fg=MUTED, font=("Segoe UI", 9),
            ).pack(anchor="w", padx=6, pady=6)

    def _add_domain_row(self, group: DomainGroup) -> None:
        valid = group.valid()
        row = tk.Frame(self.domains_frame, bg=CARD)
        row.pack(fill="x", pady=2, padx=4)

        left = tk.Frame(row, bg=CARD)
        left.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        tk.Label(left, text=group.site, bg=CARD, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        color = GREEN if valid else MUTED
        tk.Label(left, text=f"{valid} válidos / {group.total} cookies", bg=CARD,
                 fg=color, font=("Segoe UI", 8)).pack(anchor="w")

        state = "normal" if valid else "disabled"
        ttk.Button(row, text="🌐 Abrir", style="Open.TButton", state=state,
                   command=lambda s=group.site: self.open_site(s)).pack(
            side="right", padx=8)

    # ------------------------------------------------------------------ #
    # Browser launching
    # ------------------------------------------------------------------ #
    def _launch_browser(self, cookies: list[Cookie], url: str, label: str) -> None:
        if not cookies:
            self.logger.warning("Sem cookies para %s.", label)
            return
        if not playwright_available():
            self.logger.error(
                "Playwright não instalado. No terminal do PyCharm rode: "
                "pip install playwright  &&  playwright install chromium")
            return

        self.logger.info("Abrindo navegador para %s (%d cookies)…",
                         label, len(cookies))

        def worker():
            try:
                open_session(cookies, url, logger=self.logger)
            except BrowserUnavailable as exc:
                self.logger.error("%s", exc)
            except Exception as exc:  # keep the GUI alive
                self.logger.error("Erro ao abrir navegador: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    def open_service(self, profile: ServiceProfile) -> None:
        scoped = [c for c in self.cookies if profile.owns(c.registrable_domain)]
        self._launch_browser(scoped, profile.test_url, profile.label)

    def open_site(self, site: str) -> None:
        scoped = cookies_for_site(self.cookies, site)
        profile = profile_for_domain(site)
        url = profile.test_url if profile else f"https://{site}"
        self._launch_browser(scoped, url, site)

    # ------------------------------------------------------------------ #
    # Import + analysis
    # ------------------------------------------------------------------ #
    def on_import(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecione o(s) arquivo(s) de cookies",
            filetypes=[("Cookies", "*.json *.txt"), ("Todos", "*.*")],
        )
        if not paths:
            return

        batch = load_files(paths)
        for path, msg in getattr(batch, "errors", []):
            self.logger.warning("Falha ao importar %s: %s", path, msg)

        self.cookies = list(batch)
        self.file_label.config(
            text=f"{len(paths)} arquivo(s) • {len(self.cookies)} cookies")
        self.logger.info("Importados %d cookies.", len(self.cookies))
        if not self.cookies:
            self.logger.error("Nenhum cookie importado.")
            return

        self._run_analysis()

    def _run_analysis(self) -> None:
        report = analyze(self.cookies)
        self.stat_labels["total"].config(text=str(report.total))
        self.stat_labels["valid"].config(text=str(report.valid), fg=GREEN)
        self.stat_labels["expired"].config(
            text=str(report.expired), fg=YELLOW if report.expired else FG)
        self.stat_labels["invalid"].config(
            text=str(report.invalid), fg=RED if report.invalid else FG)
        self.stat_labels["duplicates"].config(text=str(report.duplicates))
        self.stat_labels["domains"].config(text=str(len(report.domains)))
        self.logger.info(report.summary())

        # Populate the Domínios tab.
        self.groups = group_by_site(self.cookies)
        self.notebook.tab(1, text=f"Domínios ({len(self.groups)})")
        self.search_var.set("")
        self._render_domains()

        self._start_session_test()

    def _start_session_test(self) -> None:
        self._clear(self.sessions_frame)
        tk.Label(self.sessions_frame, text="Validando sessões…", bg=BG,
                 fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=20, padx=6)
        self.import_btn.config(state="disabled")

        use_browser = self.browser_var.get()
        cookies = list(self.cookies)

        def worker():
            try:
                session = test_sessions(cookies, use_browser=use_browser,
                                        headless=True)
            except Exception as exc:
                self.logger.error("Erro na validação: %s", exc)
                session = None
            self.result_queue.put(session)

        threading.Thread(target=worker, daemon=True).start()

    def _render_sessions(self, session) -> None:
        self.import_btn.config(state="normal")
        self._clear(self.sessions_frame)
        if session is None or not session.outcomes:
            tk.Label(
                self.sessions_frame,
                text="Nenhuma sessão de serviço reconhecida.\n"
                     "(Perfis: Google, YouTube, GitHub.)\n\n"
                     "Use a aba \"Domínios\" para abrir qualquer site.",
                bg=BG, fg=MUTED, font=("Segoe UI", 10), justify="left",
            ).pack(anchor="w", pady=20, padx=6)
            return
        for outcome in session.outcomes:
            self._add_session_card(outcome)

    # ------------------------------------------------------------------ #
    # Queue pump (log lines + session results, drained on the main thread)
    # ------------------------------------------------------------------ #
    def _poll_queues(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass

        try:
            session = self.result_queue.get_nowait()
            self._render_sessions(session)
        except queue.Empty:
            pass

        self.root.after(150, self._poll_queues)


def main() -> None:
    setup_logging()
    root = tk.Tk()
    SessionInjectorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
