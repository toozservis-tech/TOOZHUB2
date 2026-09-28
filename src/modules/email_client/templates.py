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
    accent: str = "#187466",
    tone: str = "#edf8f4",
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
        f'<p style="margin:0 0 14px; color:#334155; font-size:16px; line-height:1.8;">{html_multiline(paragraph)}</p>'
        for paragraph in (paragraphs or [])
        if str(paragraph or "").strip()
    )
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:28px auto 18px;border-collapse:separate;">
          <tr><td bgcolor="#164b44" style="border-radius:8px;border:1px solid #24665c;border-left:5px solid #37a18d;">
            <a href="{escape(cta_url, quote=True)}" style="display:block;padding:18px 26px;color:#ffffff;text-decoration:none;font-size:16px;line-height:24px;font-weight:600;letter-spacing:0.2px;">
              {escape(cta_label)} <span aria-hidden="true" style="color:#b8e8da;padding-left:22px;font-size:22px;">&#8594;</span>
            </a>
          </td></tr>
        </table>
        <div style="text-align:center; color:#64748b; font-size:12px; line-height:1.6; margin:10px 0 0;">
          Pokud tlačítko nefunguje, otevřete odkaz ručně:<br>
          <a href="{escape(cta_url, quote=True)}" style="color:#175c50; word-break:break-all;overflow-wrap:anywhere;">{escape(cta_url)}</a>
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
<body style="margin:0;padding:0;background:#eaf0ee;font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:#17263b;">
<div style="display:none;font-size:1px;color:#eef1f5;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{escape(subtitle)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#eaf0ee"><tr><td class="outer" align="center" style="padding:40px 16px;">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;border-collapse:separate;">
<tr><td class="content" bgcolor="#e3f3f0" style="padding:32px 36px 36px;border-radius:24px 24px 0 0;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td width="70" style="vertical-align:middle;"><img src="{escape(build_app_url("/web/assets/toozservis-logo-icon.png"), quote=True)}" width="56" height="56" alt="" style="display:block;border:0;"></td><td style="vertical-align:middle;color:#123d39;font-size:23px;font-weight:bold;letter-spacing:-0.5px;">{escape(APP_DISPLAY_NAME)}<br><span style="font-size:11px;color:#385e59;font-weight:normal;letter-spacing:1px;">DIGITÁLNÍ SERVISNÍ PŘEHLED</span></td></tr></table>
<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:32px;"><tr><td style="background:#ffffff;border:1px solid #a8cec6;border-radius:20px;padding:7px 12px;color:#17564d;font-size:10px;font-weight:bold;letter-spacing:1.7px;">VŠE DŮLEŽITÉ NA JEDNOM MÍSTĚ</td></tr></table>
<h1 class="headline" style="margin:20px 0 12px;color:#123d39;font-size:36px;line-height:1.2;letter-spacing:-0.8px;font-weight:600;">{escape(title)}</h1>
<p style="margin:0;color:#385e59;font-size:16px;line-height:1.6;">{escape(subtitle)}</p>
</td></tr>
<tr><td height="5" bgcolor="#187466" style="height:5px;font-size:0;">&nbsp;</td></tr>
<tr><td class="content" bgcolor="#ffffff" style="padding:32px 36px 36px;border-left:1px solid #d9e8e1;border-right:1px solid #d9e8e1;">
<p style="margin:0 0 14px;color:#17263b;font-size:16px;line-height:1.7;">{html_multiline(intro)}</p>
{paragraph_html}{panel_html}{cta_html}
</td></tr>
<tr><td bgcolor="#f2f7f5" style="padding:22px 30px;border:1px solid #dfe5ec;border-top:1px solid #e5e9ef;border-radius:0 0 18px 18px;">
<p style="margin:0;color:#617087;font-size:12px;line-height:1.7;">{safe_footer_note}</p>
<p style="margin:14px 0 0;color:#17263b;font-size:12px;line-height:1.7;">Potřebujete poradit? <a href="mailto:info@toozservis.cz" style="color:#17263b;font-weight:bold;text-decoration:underline;">info@toozservis.cz</a></p>
</td></tr><tr><td align="center" style="padding:22px 12px;color:#748196;font-size:11px;line-height:1.7;">{escape(APP_DISPLAY_NAME)} · Digitální servisní přehled<br>Vozidla · Servisní historie · Připomínky</td></tr>
</table></td></tr></table></body></html>"""
