"""Branded vehicle history PDF. Accepts only records already filtered for the actor.

No ORM/network/file lookup of customer data is allowed in this presentation layer.
Fonts and branding are shipped with the server; reports stay in request-local memory.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO
from math import ceil, floor, log10
from pathlib import Path
from threading import Lock, BoundedSemaphore
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, HRFlowable, Image,
)
from src.core.branding import APP_DISPLAY_NAME
from .mileage_reports import summarize_mileage_timeline

INK = colors.HexColor('#172b43')
MUTED = colors.HexColor('#516174')
ACCENT = colors.HexColor('#c60063')
PAPER = colors.HexColor('#f2f5f8')
LINE = colors.HexColor('#dce3eb')
TEAL = colors.HexColor('#14776c')
WARN = colors.HexColor('#ad4418')
WIDTH = A4[0] - 84
FONT, BOLD = 'SVHistory', 'SVHistoryBold'
_FONT_LOCK = Lock()
# ReportLab shares registered font objects between requests. Serialize rendering
# to keep each document's font subsetting isolated and cap worker memory use.
_REPORT_SLOTS = BoundedSemaphore(1)


def _register_fonts():
    with _FONT_LOCK:
        if FONT not in pdfmetrics.getRegisteredFontNames():
            root = Path(__file__).with_name('report_assets')
            pdfmetrics.registerFont(TTFont(FONT, str(root / 'DejaVuSans.ttf')))
            pdfmetrics.registerFont(TTFont(BOLD, str(root / 'DejaVuSans-Bold.ttf')))
            pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=FONT, boldItalic=BOLD)


def _text(value):
    # Plain user text, never interpreted as ReportLab markup / remote image links.
    value = str(value if value is not None else '')
    return escape(''.join(c for c in value if ord(c) >= 32 or c in '\n\t')).replace('\n', '<br/>')


def number(value):
    return f'{int(value):,}'.replace(',', ' ')


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite(): return 'Neuvedeno'
        return f'{amount:,.2f}'.replace(',', ' ').replace('.', ',') + ' Kč'
    except (ValueError, InvalidOperation):
        return 'Neuvedeno'


def date_text(value):
    return value.strftime('%d. %m. %Y') if value else 'Neuvedeno'


class ReportCanvas(Canvas):
    def __init__(self, *args, generated_at, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []
        self._generated_at = generated_at

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        count = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.saveState()
            self.setStrokeColor(LINE)
            self.setLineWidth(0.6)
            self.line(42, 39, A4[0] - 42, 39)
            self.setFillColor(MUTED)
            self.setFont(FONT, 7.5)
            self.drawString(42, 26, f'{APP_DISPLAY_NAME}  |  {self._generated_at:%d. %m. %Y %H:%M} ({self._generated_at:%Z})')
            self.drawRightString(A4[0] - 42, 26, f'Strana {self._pageNumber} / {count}')
            self.restoreState()
            super().showPage()
        super().save()


class MileageChart(Flowable):
    """Vector chart with time-scaled x-axis and readable embedded-font labels."""
    def __init__(self, points):
        super().__init__()
        self.points = points
        self.width, self.height = WIDTH, 179

    def draw(self):
        c = self.canv
        left, right, bottom, top = 62, self.width - 8, 43, 165
        points = self.points
        values = [p.mileage_km for p in points]
        low, high = min(values), max(values)
        pad = max((high - low) * .12, 1000)
        low, high = max(0, low - pad), high + pad
        # Rounded kilometre intervals are easier to scan than arbitrary tick values.
        rough_step = (high - low) / 4
        magnitude = 10 ** floor(log10(rough_step))
        step = next(n * magnitude for n in (1, 2, 5, 10) if n * magnitude >= rough_step)
        low, high = floor(low / step) * step, ceil(high / step) * step
        first, last = points[0].date, points[-1].date
        duration = (last - first).total_seconds()
        def x(p): return left + ((p.date - first).total_seconds() / duration if duration else .5) * (right - left)
        def y(p): return bottom + (p.mileage_km - low) / (high - low) * (top - bottom)
        c.setFont(FONT, 8)
        for tick in range(round((high - low) / step) + 1):
            value = low + tick * step
            pos = bottom + (value - low) / (high - low) * (top - bottom)
            c.setStrokeColor(LINE); c.setLineWidth(.5); c.line(left, pos, right, pos)
            c.setFillColor(MUTED); c.drawRightString(left - 10, pos - 3, number(round(value)))
        c.setFillColor(MUTED); c.drawString(0, top + 4, 'km')
        c.setStrokeColor(INK); c.setLineWidth(1.6)
        for previous, current in zip(points, points[1:]): c.line(x(previous), y(previous), x(current), y(current))
        source_colors = {'service': INK, 'manual': ACCENT, 'stk': TEAL}
        for point in points:
            px, py = x(point), y(point)
            c.setFillColor(source_colors.get(point.source_type, INK))
            c.circle(px, py, 2.7, fill=1, stroke=0)
            if point.anomaly_flags:
                c.setStrokeColor(WARN); c.setLineWidth(1.3); c.circle(px, py, 5.2, fill=0, stroke=1)
        # Fixed time positions avoid overlapping dates in dense inspection histories.
        c.setFillColor(MUTED); c.setFont(FONT, 7.5)
        if duration:
            from datetime import timedelta
            for i in range(4):
                label = (first + timedelta(seconds=duration * i / 3)).strftime('%d.%m.%Y')
                px = left + (right-left) * i / 3
                if i == 0: c.drawString(px, bottom - 16, label)
                elif i == 3: c.drawRightString(px, bottom - 16, label)
                else: c.drawCentredString(px, bottom - 16, label)
        else:
            c.drawCentredString((left+right)/2, bottom - 16, first.strftime('%d.%m.%Y'))
        for px, color, label in [(left, INK, 'Servis'), (left+78, TEAL, 'STK / emise'), (left+196, ACCENT, 'Ruční zápis')]:
            c.setFillColor(color); c.circle(px, 8, 2.7, fill=1, stroke=0)
            c.setFillColor(MUTED); c.drawString(px+9, 5, label)
        c.setStrokeColor(WARN); c.circle(right-74, 8, 4.5, fill=0, stroke=1)
        c.drawString(right-64, 5, 'Odchylka')


CATEGORIES = {'OLEJ':'Olej a maziva', 'BRZDY':'Brzdy', 'PNEU':'Pneumatiky', 'ROZVODY':'Rozvody',
    'STK':'STK', 'DIAGNOSTIKA':'Diagnostika', 'FILTRY':'Filtry', 'CHLADICI':'Chladicí systém',
    'VYFUK':'Výfuk', 'OSVETLENI':'Osvětlení', 'KAROSERIE':'Karoserie', 'INTERIER':'Interiér',
    'ELEKTRIKA':'Elektroinstalace', 'KLIMATIZACE':'Klimatizace', 'PREVENTIVNI':'Preventivní údržba',
    'OPRAVA':'Oprava', 'JINE':'Ostatní'}


def build_vehicle_history_report(vehicle, records, points, *, generated_at=None):
    if not _REPORT_SLOTS.acquire(blocking=False):
        raise HTTPException(503, 'Právě připravujeme další přehledy. Zkuste to za chvíli.', headers={'Retry-After':'5'})
    try:
        return _build(vehicle, records, points, generated_at=generated_at)
    finally:
        _REPORT_SLOTS.release()


def _build(vehicle, records, points, *, generated_at=None):
    _register_fonts()
    generated_at = generated_at or datetime.now(ZoneInfo('Europe/Prague'))
    styles = {
        'body': ParagraphStyle('SVBody', fontName=FONT, fontSize=10, leading=15, textColor=INK, spaceAfter=7, splitLongWords=True),
        'small': ParagraphStyle('SVSmall', fontName=FONT, fontSize=8, leading=11.5, textColor=MUTED, spaceAfter=4),
        'label': ParagraphStyle('SVLabel', fontName=BOLD, fontSize=7.5, leading=11, textColor=MUTED, spaceAfter=4),
        'value': ParagraphStyle('SVValue', fontName=BOLD, fontSize=11, leading=16, textColor=INK),
        'title': ParagraphStyle('SVTitle', fontName=BOLD, fontSize=29, leading=35, textColor=INK, spaceAfter=6),
        'car': ParagraphStyle('SVCar', fontName=FONT, fontSize=16, leading=22, textColor=INK, spaceAfter=12),
        'heading': ParagraphStyle('SVHeading', fontName=BOLD, fontSize=15, leading=20, textColor=INK, spaceBefore=17, spaceAfter=8, keepWithNext=True),
        'record': ParagraphStyle('SVRecord', fontName=BOLD, fontSize=11, leading=16, textColor=INK, spaceAfter=6, keepWithNext=True),
    }
    def p(value, style='body'): return Paragraph(_text(value), styles[style])
    def table(rows, widths, *, background=None, repeat=0):
        t=Table(rows,colWidths=widths,hAlign='LEFT',repeatRows=repeat)
        commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]
        if background: commands.append(('BACKGROUND',(0,0),(-1,-1),background))
        t.setStyle(TableStyle(commands)); return t
    def field(label,value): return [p(label,'label'),p(value if value is not None and value != '' else 'Neuvedeno','value')]

    logo = Path(__file__).resolve().parents[3] / 'web/assets/toozservis-logo-icon.png'
    brand = table([[Image(str(logo),width=32,height=32),p(APP_DISPLAY_NAME,'value'),p('DIGITÁLNÍ SERVISNÍ PŘEHLED','label')]], [43,218,WIDTH-261])
    brand.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story=[brand,Spacer(1,10),HRFlowable(width='100%',thickness=2,color=ACCENT),Spacer(1,19),p('Historie vozidla','title')]
    name=' '.join(str(x) for x in (vehicle.brand,vehicle.model) if x) or vehicle.nickname or 'Vozidlo'
    story.append(p(name,'car'))
    if vehicle.nickname and vehicle.nickname.casefold()!=name.casefold(): story.append(p(vehicle.nickname,'small'))
    identity=table([[field('VIN',vehicle.vin),field('REGISTRAČNÍ ZNAČKA',vehicle.plate)]],[WIDTH*.6,WIDTH*.4],background=PAPER)
    details=table([[field('ROK VÝROBY',vehicle.year),field('MOTOR',vehicle.engine),field('STK EVIDOVANÁ DO',date_text(vehicle.stk_valid_until))]],[WIDTH*.24,WIDTH*.36,WIDTH*.4],background=PAPER)
    story.extend([identity,details,Spacer(1,12)])
    summary=summarize_mileage_timeline(points)
    amounts=[]
    for r in records:
        if r.price is not None:
            try:
                value=Decimal(str(r.price))
                if value.is_finite():amounts.append(value)
            except InvalidOperation: pass
    latest=summary['last_point']
    metrics=table([[field('ZÁZNAMŮ V HISTORII',str(len(records))),field('POSLEDNÍ EVIDOVANÝ STAV',number(latest.mileage_km)+' km' if latest else 'Neuvedeno'),field('ZADANÉ NÁKLADY',money(sum(amounts)) if amounts else 'Neuvedeno')]], [WIDTH*.28,WIDTH*.39,WIDTH*.33])
    metrics.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,-1),.6,LINE)]));story.append(metrics)
    chart_heading=p('Vývoj stavu kilometrů','heading')
    if points:
        story.append(KeepTogether([chart_heading,p('Servisní záznamy, ruční zápisy a kontroly STK / emisí v čase.','small'),MileageChart(points)]))
        story.append(p(f"Počet bodů: {len(points)}  |  {date_text(points[0].date)} až {date_text(points[-1].date)}",'small'))
        if summary['anomaly_point_count']:
            story.append(p(f"U {summary['anomaly_point_count']} bodů byla zjištěna odchylka. Označení upozorňuje na potřebu ověření, samo neprokazuje manipulaci s tachometrem.",'small'))
        else: story.append(p('Graf zachycuje evidované hodnoty; nepotvrzuje skutečný aktuální nájezd.','small'))
    else: story.extend([chart_heading,p('Zatím chybí záznam s datem a stavem kilometrů. Po jeho doplnění se zde zobrazí graf.','body')])
    story.append(p('Servisní historie','heading'))
    if not records: story.append(p('Dosud nejsou evidovány servisní záznamy.','body'))
    for index,record in enumerate(records,1):
        category=CATEGORIES.get(record.category,record.category or 'Ostatní')
        title=p(f'{index:02d}  |  {date_text(record.performed_at)}  /  {category}','record')
        meta=p('  |  '.join([f"Stav: {number(record.mileage)} km" if record.mileage is not None else 'Stav km neuveden',f"Částka: {money(record.price)}" if record.price is not None else 'Částka neuvedena']),'small')
        # Keep only the heading/meta/first paragraph together; long notes may split safely.
        title.keepWithNext=True; meta.keepWithNext=True
        story.extend([title,meta,p(record.description or 'Bez popisu')])
        if record.note: story.append(p('Poznámka: '+str(record.note),'body'))
        story.extend([Spacer(1,4),HRFlowable(width='100%',thickness=.5,color=LINE),Spacer(1,10)])
    if points:
        evidence_intro = p('Přehled bodů použitých v grafu. Údaje se mohou vztahovat k téže návštěvě servisu.','small')
        evidence_intro.keepWithNext = True
        story.extend([p('Podklady ke grafu','heading'), evidence_intro])
        rows=[[p('DATUM','label'),p('STAV KM','label'),p('ZDROJ','label'),p('KONTROLA','label')]]
        for point in points:
            source={'stk':'STK / emise','service':'Servis','manual':'Ruční zápis'}.get(point.source_type,'Záznam')
            flags={'rollback':'Pokles km','suspicious_jump':'Velký nárůst','duplicate':'Shodný zápis'}
            label=', '.join(flags.get(flag,'Odchylka') for flag in point.anomaly_flags) or '-'
            rows.append([p(date_text(point.date),'small'),p(number(point.mileage_km),'small'),p(source,'small'),p(label,'small')])
        evidence=table(rows,[WIDTH*.24,WIDTH*.22,WIDTH*.26,WIDTH*.28],repeat=1)
        evidence.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PAPER),('LINEBELOW',(0,0),(-1,0),.7,LINE),('LINEBELOW',(0,1),(-1,-1),.3,LINE)]))
        story.append(evidence)
    story.extend([Spacer(1,10),p('Rozsah přehledu','record'),p('Dokument obsahuje údaje dostupné v aplikaci v okamžiku exportu a v rozsahu oprávnění přihlášeného účtu. Nezadané náklady nejsou zahrnuty v součtu. Podrobnosti a soukromé doklady předchozích vlastníků mohou být skryté.','small')])
    stream=BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=32,bottomMargin=54,
        title=f'{APP_DISPLAY_NAME} - Historie vozidla',author=APP_DISPLAY_NAME,subject='Servisní historie a evidované stavy kilometrů')
    def page_header(canvas,document):
        if document.page>1:
            canvas.saveState();canvas.setFont(FONT,8);canvas.setFillColor(MUTED)
            canvas.drawString(42,A4[1]-22,f'{APP_DISPLAY_NAME}  /  Historie vozidla');canvas.restoreState()
    doc.build(story,onFirstPage=page_header,onLaterPages=page_header,
              canvasmaker=lambda *a,**kw:ReportCanvas(*a,generated_at=generated_at,**kw))
    return stream.getvalue()
