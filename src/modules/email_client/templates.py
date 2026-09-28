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
              <td style="padding:10px 0; color:#64748b; font-size:13px; width:38%;padding-right:12px; vertical-align:top;">{escape(str(label))}</td>
              <td style="padding:10px 0; color:#0f172a; font-size:14px; font-weight:600;word-break:break-word;overflow-wrap:anywhere;">{safe_value}</td>
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
          <a href="{escape(cta_url, quote=True)}" style="display:inline-block; background:#ff9300; color:#17263b; text-decoration:none; font-weight:700; padding:14px 22px; border-radius:10px;">
            {escape(cta_label)}
          </a>
        </div>
        <div style="text-align:center; color:#64748b; font-size:12px; line-height:1.6; margin:10px 0 0;">
          Pokud tlačítko nefunguje, otevřete odkaz ručně:<br>
          <a href="{escape(cta_url, quote=True)}" style="color:#2563eb; word-break:break-all;overflow-wrap:anywhere;">{escape(cta_url)}</a>
        </div>
        """
    safe_footer_note = html_multiline(
        footer_note
        or f"Tento e-mail byl odeslán z aplikace {APP_DISPLAY_NAME}. Pokud jste tuto akci neočekávali, zkontrolujte svůj účet nebo kontaktujte podporu."
    )
    return f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light"><title>{escape(title)} · {escape(APP_DISPLAY_NAME)}</title>
<style>@media only screen and (max-width:600px){{.outer{{padding:16px 8px!important}}.content{{padding:26px 20px!important}}.headline{{font-size:28px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#eef1f5;font-family:Arial,Helvetica,sans-serif;color:#17263b;">
<div style="display:none;font-size:1px;color:#eef1f5;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{escape(subtitle)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#eef1f5"><tr><td class="outer" align="center" style="padding:40px 16px;">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;border-collapse:separate;">
<tr><td bgcolor="#17263b" style="padding:28px 32px;border-radius:18px 18px 0 0;border-bottom:4px solid #ff9300;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="color:#ffffff;font-size:27px;font-weight:800;letter-spacing:-1px;"><img src="{escape(build_app_url("/web/assets/toozservis-logo-icon.png"), quote=True)}" width="56" height="56" alt="" style="display:inline-block;vertical-align:middle;border:0;margin-right:12px;"> <span style="vertical-align:middle;font-size:23px;letter-spacing:-0.5px;">{escape(APP_DISPLAY_NAME)}</span></td><td align="right" style="color:#cbd5e1;font-size:11px;line-height:1.5;">VAŠE VOZIDLA.<br>VŠE POD KONTROLOU.</td></tr></table>
</td></tr>
<tr><td class="content" bgcolor="#ffffff" style="padding:34px 36px 36px;border-left:1px solid #dfe5ec;border-right:1px solid #dfe5ec;">
<p style="margin:0 0 12px;color:#785000;font-size:11px;font-weight:bold;letter-spacing:1.6px;text-transform:uppercase;">ZPRÁVA Z APLIKACE</p>
<h1 class="headline" style="margin:0 0 12px;color:#17263b;font-size:32px;line-height:1.18;letter-spacing:-0.6px;">{escape(title)}</h1>
<p style="margin:0 0 26px;padding-bottom:24px;border-bottom:1px solid #e5e9ef;color:#617087;font-size:16px;line-height:1.6;">{escape(subtitle)}</p>
<p style="margin:0 0 14px;color:#17263b;font-size:16px;line-height:1.7;">{html_multiline(intro)}</p>
{paragraph_html}{panel_html}{cta_html}
</td></tr>
<tr><td bgcolor="#f8fafc" style="padding:22px 30px;border:1px solid #dfe5ec;border-top:1px solid #e5e9ef;border-radius:0 0 18px 18px;">
<p style="margin:0;color:#617087;font-size:12px;line-height:1.7;">{safe_footer_note}</p>
<p style="margin:14px 0 0;color:#17263b;font-size:12px;line-height:1.7;">Potřebujete poradit? <a href="mailto:info@toozservis.cz" style="color:#17263b;font-weight:bold;text-decoration:underline;">info@toozservis.cz</a></p>
</td></tr><tr><td align="center" style="padding:22px 12px;color:#748196;font-size:11px;line-height:1.7;">{escape(APP_DISPLAY_NAME)} · Digitální servisní přehled<br>Vozidla · Servisní historie · Připomínky</td></tr>
</table></td></tr></table></body></html>"""
