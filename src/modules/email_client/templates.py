from __future__ import annotations

from html import escape
from typing import Iterable, Mapping, Sequence

from src.core.branding import APP_DISPLAY_NAME
from src.core.config import PUBLIC_API_BASE_URL


def build_app_url(path: str = "/web/index.html") -> str:
    base = str(PUBLIC_API_BASE_URL or "").strip().rstrip("/")
    if not base:
        return f"https://hub.toozservis.cz{path}"
    if base.endswith("/web/index.html") and path == "/web/index.html":
        return base
    if base.endswith("/index.html") and path == "/web/index.html":
        return base
    return f"{base}{path}"


def html_multiline(text: str | None) -> str:
    return "<br>".join(escape(str(text or "")).splitlines()) or "Neuvedeno"


def render_rows(rows: Sequence[tuple[str, object]]) -> str:
    rendered = []
    for label, value in rows:
        safe_value = escape(str(value if value not in (None, "") else "Neuvedeno"))
        rendered.append(
            f"""
            <tr>
              <td style="padding:10px 0; color:#64748b; font-size:13px; width:38%; vertical-align:top;">{escape(str(label))}</td>
              <td style="padding:10px 0; color:#0f172a; font-size:14px; font-weight:600;">{safe_value}</td>
            </tr>
            """
        )
    return "".join(rendered)


def render_panel(
    *,
    title: str,
    rows: Sequence[tuple[str, object]] | None = None,
    message: str | None = None,
    raw_html: str | None = None,
    accent: str = "#f59e0b",
    tone: str = "#fff7ed",
) -> str:
    rows_html = ""
    if rows:
        rows_html = f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
          {render_rows(rows)}
        </table>
        """
    message_html = ""
    if message:
        message_html = (
            f'<div style="color:#334155; font-size:14px; line-height:1.65; white-space:normal;">{html_multiline(message)}</div>'
        )
    if raw_html:
        message_html += raw_html
    return f"""
    <div style="background:{tone}; border:1px solid #e2e8f0; border-left:4px solid {accent}; border-radius:18px; padding:18px 20px; margin:16px 0;">
      <div style="font-size:15px; font-weight:700; color:#0f172a; margin:0 0 10px;">{escape(title)}</div>
      {rows_html}
      {message_html}
    </div>
    """


def render_list(items: Iterable[str]) -> str:
    parts = [
        f'<li style="margin:0 0 8px; color:#334155;">{html_multiline(item)}</li>'
        for item in items
        if str(item or "").strip()
    ]
    if not parts:
        return ""
    return f'<ul style="margin:12px 0 0 18px; padding:0;">{"".join(parts)}</ul>'


def render_email_layout(
    *,
    title: str,
    subtitle: str,
    intro: str,
    panels: Sequence[str] | None = None,
    paragraphs: Sequence[str] | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
    accent: str = "#f59e0b",
    footer_note: str | None = None,
) -> str:
    panel_html = "".join(panels or [])
    paragraph_html = "".join(
        f'<p style="margin:0 0 14px; color:#334155; font-size:15px; line-height:1.7;">{html_multiline(paragraph)}</p>'
        for paragraph in (paragraphs or [])
        if str(paragraph or "").strip()
    )
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <div style="margin:24px 0 10px; text-align:center;">
          <a href="{escape(cta_url, quote=True)}" style="display:inline-block; background:{accent}; color:#111827; text-decoration:none; font-weight:700; padding:14px 22px; border-radius:14px;">
            {escape(cta_label)}
          </a>
        </div>
        <div style="text-align:center; color:#64748b; font-size:12px; line-height:1.6; margin:10px 0 0;">
          Pokud tlačítko nefunguje, otevřete odkaz ručně:<br>
          <a href="{escape(cta_url, quote=True)}" style="color:#2563eb; word-break:break-all;">{escape(cta_url)}</a>
        </div>
        """
    safe_footer_note = html_multiline(
        footer_note
        or f"Tento e-mail byl odeslán z aplikace {APP_DISPLAY_NAME}. Pokud jste tuto akci neočekávali, zkontrolujte svůj účet nebo kontaktujte podporu."
    )
    return f"""
<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)} · {APP_DISPLAY_NAME}</title>
</head>
<body style="margin:0; padding:24px 12px; background:#eef2ff; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:680px; margin:0 auto;">
    <div style="background:linear-gradient(180deg, #111827 0%, #1f2937 100%); border-radius:28px; padding:28px; box-shadow:0 20px 60px rgba(15,23,42,0.22);">
      <div style="display:inline-block; background:rgba(245,158,11,0.16); color:#fbbf24; border:1px solid rgba(251,191,36,0.28); padding:7px 12px; border-radius:999px; font-size:12px; font-weight:700; letter-spacing:0.02em;">
        {escape(APP_DISPLAY_NAME)}
      </div>
      <h1 style="margin:18px 0 6px; color:#ffffff; font-size:30px; line-height:1.2;">{escape(title)}</h1>
      <p style="margin:0 0 24px; color:#cbd5e1; font-size:15px; line-height:1.6;">{escape(subtitle)}</p>

      <div style="background:#ffffff; border-radius:22px; padding:24px;">
        <p style="margin:0 0 14px; color:#0f172a; font-size:15px; line-height:1.7;">{html_multiline(intro)}</p>
        {paragraph_html}
        {panel_html}
        {cta_html}
      </div>

      <div style="padding:16px 6px 4px; text-align:center; color:#cbd5e1; font-size:12px; line-height:1.7;">
        {safe_footer_note}
      </div>
    </div>
  </div>
</body>
</html>
"""
