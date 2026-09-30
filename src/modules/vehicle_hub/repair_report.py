"""Private PDF photo record, with bounded resources and verified original files."""
import hashlib
import io
from datetime import datetime
from html import escape
from pathlib import Path
from threading import Lock, BoundedSemaphore

from fastapi import HTTPException
from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage, PageBreak, Table, TableStyle

from src.core.branding import APP_DISPLAY_NAME
from src.core.file_storage import cached_file

_FONT_LOCK = Lock()
_REPORT_SLOT = BoundedSemaphore(1)
MAX_REPORT_PHOTOS = 100
MAX_REPORT_ORIGINAL_BYTES = 120 * 1024 * 1024
MAX_PHOTO_BYTES = 12 * 1024 * 1024
PHASES = {'before': 'Před opravou', 'during': 'V průběhu opravy', 'after': 'Po opravě'}


def _font():
    with _FONT_LOCK:
        if 'RepairSans' not in pdfmetrics.getRegisteredFontNames():
            font = next((p for p in [
                Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
                Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
            ] if p.is_file()), None)
            if font is None:
                raise HTTPException(503, 'Písmo pro český protokol není dostupné.')
            pdfmetrics.registerFont(TTFont('RepairSans', str(font)))
    return 'RepairSans'


def _verified_preview(photo, root):
    target = (root / photo.file_path).resolve()
    if target.parent != root.resolve():
        raise HTTPException(404, 'Fotografie není dostupná.')
    cached_file(target)
    if not target.is_file() or target.stat().st_size > MAX_PHOTO_BYTES:
        raise HTTPException(409, 'Nelze sestavit úplný protokol: fotografie chybí nebo má neplatnou velikost.')
    content = target.read_bytes()
    if len(content) != photo.size_bytes or hashlib.sha256(content).hexdigest() != photo.sha256:
        raise HTTPException(409, 'Nelze sestavit úplný protokol: fotografie neprošla kontrolou integrity.')
    try:
        with Image.open(io.BytesIO(content)) as original:
            if original.width * original.height > 32_000_000:
                raise ValueError('Image exceeds allowed resolution')
            preview = ImageOps.exif_transpose(original)
            preview.thumbnail((1600, 1600))
            if preview.mode != 'RGB':
                background = Image.new('RGB', preview.size, 'white')
                if preview.mode == 'RGBA':
                    background.paste(preview, mask=preview.getchannel('A'))
                else:
                    background.paste(preview.convert('RGB'))
                preview = background
            stream = io.BytesIO()
            preview.save(stream, format='JPEG', quality=85)
            stream.seek(0)
            return stream
    except Exception:
        raise HTTPException(409, 'Nelze sestavit protokol: uloženou fotografii nelze přečíst.') from None


def build_repair_report(session, vehicle, evidence, photo_root):
    if not _REPORT_SLOT.acquire(blocking=False):
        raise HTTPException(503, 'Právě připravujeme jiný protokol. Zkuste to za chvíli.', headers={'Retry-After': '5'})
    try:
        return _build_repair_report(session, vehicle, evidence, photo_root)
    finally:
        _REPORT_SLOT.release()


def _build_repair_report(session, vehicle, evidence, photo_root):
    if len(evidence) > MAX_REPORT_PHOTOS or sum(p.size_bytes for p in evidence) > MAX_REPORT_ORIGINAL_BYTES:
        raise HTTPException(422, 'Fotodokumentace je pro jeden protokol příliš velká. Fotografie můžete stáhnout jednotlivě.')
    if any(p.phase not in PHASES for p in evidence):
        raise HTTPException(409, 'Nelze sestavit úplný protokol: některá fotografie má neznámou fázi opravy.')
    font = _font()
    ink, muted, accent = colors.HexColor('#163f3a'), colors.HexColor('#536b65'), colors.HexColor('#eef5f2')
    styles = {
        'body': ParagraphStyle('body', fontName=font, fontSize=10, leading=15, textColor=ink, spaceAfter=8),
        'title': ParagraphStyle('title', fontName=font, fontSize=26, leading=32, textColor=ink, spaceAfter=18),
        'heading': ParagraphStyle('heading', fontName=font, fontSize=17, leading=23, textColor=ink, spaceAfter=12),
        'small': ParagraphStyle('small', fontName=font, fontSize=8, leading=12, textColor=muted, spaceAfter=5),
        'hash': ParagraphStyle('hash', fontName=font, fontSize=7, leading=10, textColor=muted, splitLongWords=True),
    }
    def p(text, style='body'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])
    stream = io.BytesIO()
    title = f'{APP_DISPLAY_NAME} - předávací protokol'
    logo = Path(__file__).resolve().parents[3] / 'web/assets/toozservis-logo-icon.png'
    if logo.is_file():
        brand = Table([[PDFImage(str(logo), width=38, height=38), p(APP_DISPLAY_NAME, 'heading')]],
                      colWidths=[52, 471], hAlign='LEFT')
        brand.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'), ('LEFTPADDING',(0,0),(-1,-1),0)]))
    else:
        brand = p(APP_DISPLAY_NAME, 'heading')
    story = [brand, Spacer(1,16), p('Fotodokumentace opravy', 'title'), p(session.title, 'heading')]
    info = [('Vozidlo', vehicle.plate or f'Vozidlo {vehicle.id}'),
            ('Značka a model', ' '.join(filter(None, [vehicle.brand, vehicle.model])) or 'Neuvedeno'),
            ('Číslo dokumentace', str(session.id)),
            ('Vytvořeno na serveru (UTC)', session.created_at.strftime('%d.%m.%Y %H:%M')),
            ('Exportováno (UTC)', datetime.utcnow().strftime('%d.%m.%Y %H:%M'))]
    table = Table([[p(k, 'small'), p(v)] for k, v in info], colWidths=[180, 343], hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), accent), ('VALIGN',(0,0),(-1,-1),'TOP'),
                               ('LEFTPADDING',(0,0),(-1,-1),12), ('TOPPADDING',(0,0),(-1,-1),8)]))
    story += [table, Spacer(1,20), p('Přehled dokumentace', 'heading')]
    for phase, label in PHASES.items():
        count = sum(photo.phase == phase for photo in evidence)
        story += [p(f'{label} - počet snímků: {count}' if count else f'{label}: bez fotografií')]
    story += [Spacer(1,10), p('Dokument shrnuje fotografie uložené k této opravě. Náhledy jsou zmenšené pro tisk; kontrolní otisk se vztahuje k původnímu uloženému souboru. Čas nahrání zaznamenal server. Čas pořízení i údaj o zdroji dodal telefon a nejsou nezávislým potvrzením.', 'small'),
              Spacer(1,16), p('Předání vozidla', 'heading'), p('Předávající: __________________________________________'),
              p('Přebírající: ___________________________________________'), p('Datum předání: _______________________________________'),
              p('Podpis předávajícího: ______________  Podpis přebírajícího: ______________'),
              p('Poznámka při předání: __________________________________'),
              p('_____________________________________________________')]
    for phase, label in PHASES.items():
        for photo in (item for item in evidence if item.phase == phase):
            image = PDFImage(_verified_preview(photo, photo_root))
            image._restrictSize(523, 370)
            image.hAlign = 'LEFT'
            story += [PageBreak(), p(label, 'heading'), p(f'Snímek {photo.id} • Dokumentace {session.id}', 'small'),
                      image, Spacer(1,14), p(photo.note or 'Bez poznámky'),
                      p('Autor: '+str(photo.author_name or f'Účet {photo.author_id}'), 'small'),
                      p('Nahráno na server (UTC): '+photo.uploaded_at.strftime('%d.%m.%Y %H:%M:%S'), 'small'),
                      p('Zdroj podle telefonu: '+('Fotoaparát' if photo.source == 'camera' else 'Fotogalerie'), 'small')]
            if photo.captured_at:
                story += [p('Čas podle telefonu (UTC): '+photo.captured_at.strftime('%d.%m.%Y %H:%M:%S'), 'small')]
            story += [p('Kontrolní otisk původního souboru SHA-256', 'small'), p(photo.sha256, 'hash')]
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#d6e5df'))
        canvas.line(36, 38, A4[0]-36, 38)
        canvas.setFont(font,8)
        canvas.setFillColor(muted)
        canvas.drawString(36,24,f'{APP_DISPLAY_NAME} • Protokol {session.id}')
        canvas.drawRightString(A4[0]-36,24,f'Strana {doc.page}')
    SimpleDocTemplate(stream, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=52,
                      title=title, author=APP_DISPLAY_NAME).build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
