from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from PyPDF2 import PdfReader
import pytest

from src.modules.vehicle_hub.vehicle_history_report import build_vehicle_history_report
from src.modules.vehicle_hub.mileage_reports import MileageTimelinePoint


def vehicle(**kwargs):
    data=dict(id=1, brand='ŠKODA', model='SUPERB', nickname=None, year=2011, vin='TMBJF73T2B9000001',plate='UKÁZKA',engine='CFGB',stk_valid_until=date(2028,4,22))
    data.update(kwargs);return SimpleNamespace(**data)


def record(**kwargs):
    data=dict(performed_at=datetime(2026,1,2),category='OLEJ',description='Výměna oleje a těsnění. Příliš žluťoučký kůň úpěl ďábelské ódy.',mileage=0,price=0,note='Kontrola: Řízení, čepy a příslušenství.')
    data.update(kwargs);return SimpleNamespace(**data)


def points(count=7):
    return [MileageTimelinePoint(datetime(2014,1,1)+timedelta(days=i*365),45000+i*48000,'stk','STK / Pravidelná',f'stk:{i}',True) for i in range(count)]


def build(records=None, pts=None, car=None):
    return build_vehicle_history_report(car or vehicle(),records or [],pts or [],generated_at=datetime(2026,10,1,10,0,tzinfo=ZoneInfo('Europe/Prague')))


def text_of(pdf):return '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)


def test_unicode_fonts_and_document_brand_are_preserved():
    pdf=build([record()],points())
    text=text_of(pdf)
    for value in ['Evidence Vozidel','Historie vozidla','ŠKODA SUPERB','Příliš žluťoučký kůň úpěl ďábelské ódy.','Řízení, čepy','0,00 Kč','0 km','22. 04. 2028']:
        assert value in text
    assert '\u25a0' not in text and '\ufffd' not in text
    fonts=[font.get_object() for page in PdfReader(BytesIO(pdf)).pages for font in page['/Resources']['/Font'].values()]
    assert any('/FontFile2' in font.get('/FontDescriptor',{}).get_object() for font in fonts if '/FontDescriptor' in font)


def test_chart_heading_axes_and_legend_fit_together_on_first_page():
    reader=PdfReader(BytesIO(build([record()],points())))
    first=reader.pages[0].extract_text()
    for label in ['Vývoj stavu kilometrů','STK / emise','Ruční zápis',points()[0].date.strftime('%d.%m.%Y'),points()[-1].date.strftime('%d.%m.%Y')]:
        assert label in first
    assert len(reader.pages)<=2
    for i,page in enumerate(reader.pages,1):
        assert f'Strana {i} / {len(reader.pages)}' in page.extract_text()


def test_empty_and_single_point_histories_render_without_made_up_values():
    empty=build()
    assert len(PdfReader(BytesIO(empty)).pages)==1
    assert 'Zatím chybí záznam' in text_of(empty)
    one=build([],points(1))
    assert '45 000' in text_of(one)
    assert 'Počet bodů: 1' in text_of(one)


def test_long_history_long_notes_and_unknown_dates_are_not_truncated():
    records=[record(description=f'Záznam {i}: '+('Oprava čerpadla a řízení. '*30),note=('Řádek s dlouhou poznámkou.\n'*15)+f'KONEC-{i}',performed_at=None if i==3 else datetime(2026,1,2)) for i in range(16)]
    reader=PdfReader(BytesIO(build(records,points(90))))
    text='\n'.join(p.extract_text() for p in reader.pages)
    for i in range(16):assert f'KONEC-{i}' in text
    assert len(reader.pages)<30
    assert all('Strana' in p.extract_text() for p in reader.pages)


def test_text_is_literal_and_prices_keep_decimals_without_treating_missing_as_zero():
    pdf=build([record(price=1234.56,description='<img src="https://example.invalid/private"/> & $ \\ text',note=''),record(price=None)],[])
    text=text_of(pdf)
    assert '1 234,56 Kč' in text
    assert '<img src=' in text and '& $ \\ text' in text
    assert 'Částka neuvedena' in text


def test_evidence_heading_stays_with_first_table_row_on_page_boundary():
    records = [record(description=f'Oprava č. {i+1}: '+('Kontrola podvozku, řízení a čerpadla. '*9),note='Poznámka k provedené práci. '*24) for i in range(12)]
    pages = PdfReader(BytesIO(build(records, points(45)))).pages
    for page in pages:
        text = page.extract_text()
        if 'Podklady ke grafu' in text:
            assert 'DATUM' in text and '45 000' in text


def test_many_points_on_same_day_and_rollback_are_visible():
    pts=points(3)
    for p in pts:p.date=datetime(2026,10,1)
    pts[-1].mileage_km=20000;pts[-1].anomaly_flags=['rollback'];pts[-1].anomaly='rollback'
    text=text_of(build([],pts))
    assert 'Pokles km' in text and 'samo neprokazuje manipulaci' in text


def test_busy_renderer_asks_client_to_retry_and_recovers_after_failure(monkeypatch):
    from fastapi import HTTPException
    from src.modules.vehicle_hub import vehicle_history_report as report
    with report._REPORT_SLOTS:
        with pytest.raises(HTTPException) as failure:
            build()
        assert failure.value.status_code == 503
        assert failure.value.headers['Retry-After'] == '5'
    original = report._build
    def fail(*args, **kwargs):
        raise ValueError('Invalid report input')
    monkeypatch.setattr(report, '_build', fail)
    with pytest.raises(ValueError):
        build()
    monkeypatch.setattr(report, '_build', original)
    assert build().startswith(b'%PDF')
