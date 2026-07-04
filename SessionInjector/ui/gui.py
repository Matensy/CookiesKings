"""Desktop GUI (Tkinter).

A single-window front-end over the same ``core`` API used by the CLI. Tkinter
ships with Python, so this needs no extra install. Long-running work (analysis
and browser tests) runs on a background thread so the window never freezes, and
log records are streamed into the on-screen log panel.

Run it with the root launcher:  python run_gui.py
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from ..cookies.analyzer import analyze
from ..cookies.loader import load_files
from ..cookies.models import Severity
from ..core.logging_config import get_logger, setup_logging
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
        self.cookies = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.result_queue: "queue.Queue" = queue.Queue()

        root.title("Session Injector")
        root.geometry("860x640")
        root.minsize(720, 520)
        root.configure(bg=BG)

        self._setup_logging()
        self._build_style()
        self._build_header()
        self._build_body()
        self._build_log()
        self._poll_log_queue()

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
        style.configure("TButton", padding=8, font=("Segoe UI", 10))
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#4a7be0")])
        style.configure("TCheckbutton", background=BG, foreground=FG,
                        font=("Segoe UI", 10))
        style.configure("Horizontal.TProgressbar", troughcolor=CARD,
                        background=ACCENT, thickness=14)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(header, text="🍪  Session Injector", bg=BG, fg=FG,
                 font=("Segoe UI", 18, "bold")).pack(side="left")

        tk.Label(
            header,
            text="Uso autorizado — apenas com suas próprias contas",
            bg=BG, fg=MUTED, font=("Segoe UI", 9),
        ).pack(side="right", pady=(8, 0))

        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 8))

        self.import_btn = ttk.Button(
            bar, text="📂  Importar cookies…", style="Accent.TButton",
            command=self.on_import,
        )
        self.import_btn.pack(side="left")

        self.browser_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="Testar no navegador (abre o Chromium)",
            variable=self.browser_var,
        ).pack(side="left", padx=12)

        self.headed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="Mostrar a janela do navegador",
            variable=self.headed_var,
        ).pack(side="left")

        self.file_label = tk.Label(bar, text="Nenhum arquivo carregado",
                                   bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.file_label.pack(side="right")

    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        # Left: analysis summary cards.
        left = tk.Frame(body, bg=BG, width=240)
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

        # Right: session results (scrollable).
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="SESSÕES", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))

        self.sessions_frame = tk.Frame(right, bg=BG)
        self.sessions_frame.pack(fill="both", expand=True)
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

    def _build_log(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(frame, text="LOGS", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.log_text = tk.Text(frame, height=7, bg="#15161c", fg="#c8ccda",
                                font=("Consolas", 9), relief="flat", wrap="word")
        self.log_text.pack(fill="x", pady=(4, 0))
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Sessions panel
    # ------------------------------------------------------------------ #
    def _clear_sessions(self) -> None:
        for w in self.sessions_frame.winfo_children():
            w.destroy()

    def _placeholder(self) -> None:
        tk.Label(
            self.sessions_frame,
            text="Importe um arquivo de cookies para começar.\n\n"
                 "Formatos aceitos: Netscape (cookies.txt) e JSON.",
            bg=BG, fg=MUTED, font=("Segoe UI", 10), justify="left",
        ).pack(anchor="w", pady=20)

    def _add_session_card(self, outcome) -> None:
        h = outcome.health
        v = outcome.validation
        color = _score_color(h.score)

        card = tk.Frame(self.sessions_frame, bg=CARD)
        card.pack(fill="x", pady=5)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(top, text=outcome.profile.label, bg=CARD, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(top, text=f"{h.stars}  {h.score}/100", bg=CARD, fg=color,
                 font=("Segoe UI", 12, "bold")).pack(side="right")

        bar = ttk.Progressbar(card, maximum=100, value=h.score,
                              style="Horizontal.TProgressbar")
        bar.pack(fill="x", padx=12, pady=(0, 6))

        info = f"Status: {v.status.value}  •  {h.grade}"
        if v.missing_required:
            info += f"  •  faltando: {', '.join(v.missing_required)}"
        tk.Label(card, text=info, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9), justify="left", wraplength=520).pack(
            anchor="w", padx=12, pady=(0, 10))

    # ------------------------------------------------------------------ #
    # Actions
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
        self.file_label.config(text=f"{len(paths)} arquivo(s) • {len(self.cookies)} cookies")
        self.logger.info("Importados %d cookies.", len(self.cookies))

        if not self.cookies:
            self.logger.error("Nenhum cookie importado.")
            return

        self._run_analysis()

    def _run_analysis(self) -> None:
        report = analyze(self.cookies)
        self.stat_labels["total"].config(text=str(report.total))
        self.stat_labels["valid"].config(text=str(report.valid), fg=GREEN)
        self.stat_labels["expired"].config(text=str(report.expired),
                                           fg=YELLOW if report.expired else FG)
        self.stat_labels["invalid"].config(text=str(report.invalid),
                                           fg=RED if report.invalid else FG)
        self.stat_labels["duplicates"].config(text=str(report.duplicates))
        self.stat_labels["domains"].config(text=str(len(report.domains)))
        self.logger.info(report.summary())

        errors = [i for i in report.issues if i.severity is Severity.ERROR]
        for issue in errors[:8]:
            self.logger.warning(issue.message)

        self._start_session_test()

    def _start_session_test(self) -> None:
        self._clear_sessions()
        tk.Label(self.sessions_frame, text="Validando sessões…", bg=BG,
                 fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=20)
        self.import_btn.config(state="disabled")

        use_browser = self.browser_var.get()
        headed = self.headed_var.get()
        cookies = list(self.cookies)

        def worker():
            try:
                session = test_sessions(
                    cookies, use_browser=use_browser, headless=not headed,
                )
            except Exception as exc:  # keep the GUI alive on any failure
                self.logger.error("Erro na validação: %s", exc)
                session = None
            # Hand the result back to the main thread via the queue; never
            # touch Tk widgets from a background thread.
            self.result_queue.put(session)

        threading.Thread(target=worker, daemon=True).start()

    def _render_sessions(self, session) -> None:
        self.import_btn.config(state="normal")
        self._clear_sessions()
        if session is None or not session.outcomes:
            tk.Label(
                self.sessions_frame,
                text="Nenhuma sessão de serviço reconhecida nestes cookies.\n"
                     "(Perfis atuais: Google, YouTube, GitHub.)",
                bg=BG, fg=MUTED, font=("Segoe UI", 10), justify="left",
            ).pack(anchor="w", pady=20)
            return
        for outcome in session.outcomes:
            self._add_session_card(outcome)

    # ------------------------------------------------------------------ #
    # Log pump
    # ------------------------------------------------------------------ #
    def _poll_log_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass

        # Session results come back on their own queue, drained on the main
        # thread so all widget updates happen where Tk expects them.
        try:
            session = self.result_queue.get_nowait()
            self._render_sessions(session)
        except queue.Empty:
            pass

        self.root.after(150, self._poll_log_queue)


def main() -> None:
    setup_logging()
    root = tk.Tk()
    SessionInjectorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
