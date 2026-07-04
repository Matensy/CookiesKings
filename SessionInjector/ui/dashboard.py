"""Dashboard rendering.

Pure formatting helpers that turn analysis / test results into text blocks for
the CLI. Kept UI-framework-agnostic so a future Tkinter/Qt GUI can reuse the
same data (the ``as_dict`` methods) without depending on these strings.
"""
from __future__ import annotations

from ..cookies.models import AnalysisReport, Severity
from ..core.session_tester import TestSession


def render_analysis(report: AnalysisReport) -> str:
    lines = [
        "┌─ Cookie Analysis ─────────────────────────────",
        f"│ Total cookies : {report.total}",
        f"│ Valid         : {report.valid}",
        f"│ Expired       : {report.expired}",
        f"│ Invalid       : {report.invalid}",
        f"│ Duplicates    : {report.duplicates}",
        f"│ Domains       : {len(report.domains)}",
    ]
    errors = [i for i in report.issues if i.severity is Severity.ERROR]
    warnings = [i for i in report.issues if i.severity is Severity.WARNING]
    if errors:
        lines.append("│")
        lines.append(f"│ Errors ({len(errors)}):")
        for issue in errors[:10]:
            lines.append(f"│   ✖ {issue.message}")
        if len(errors) > 10:
            lines.append(f"│   … and {len(errors) - 10} more")
    if warnings:
        lines.append("│")
        lines.append(f"│ Warnings ({len(warnings)}):")
        for issue in warnings[:10]:
            lines.append(f"│   ! {issue.message}")
        if len(warnings) > 10:
            lines.append(f"│   … and {len(warnings) - 10} more")
    lines.append("└───────────────────────────────────────────────")
    return "\n".join(lines)


def render_session(session: TestSession) -> str:
    if not session.outcomes:
        return "No recognised service sessions found in the imported cookies."

    lines = ["┌─ Session Test ────────────────────────────────"]
    for outcome in session.outcomes:
        h = outcome.health
        v = outcome.validation
        lines.append(f"│ {outcome.profile.label}")
        lines.append(f"│   Status : {v.status.value}")
        if v.final_url:
            lines.append(f"│   URL    : {v.final_url}")
        if v.missing_required:
            lines.append(f"│   Missing: {', '.join(v.missing_required)}")
        lines.append(f"│   Health : {h.stars}  {h.score}/100  ({h.grade})")
        for factor, points in h.contributions.items():
            lines.append(f"│      • {factor:<12} {points:>5.1f} pts")
        lines.append("│")
    lines.append("└───────────────────────────────────────────────")
    return "\n".join(lines)
