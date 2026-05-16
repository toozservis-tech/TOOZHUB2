from __future__ import annotations

from io import BytesIO
from typing import Iterable, Mapping

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas


def render_service_invoice_pdf(payload: Mapping[str, object]) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    page_h = A4[1]
    page_w = A4[0]
    margin = 18 * mm
    col_gap = 8 * mm
    mid_x = page_w / 2 + 2 * mm
    x = margin
    y = page_h - 20 * mm

    def draw_str(xx: float, yy: float, text: str, *, size: int = 11, bold: bool = False) -> None:
        canvas.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        canvas.drawString(xx, yy, str(text or "")[:120])

    def line(text: str, *, size: int = 11, bold: bool = False, gap: float = 7) -> None:
        nonlocal y
        draw_str(x, y, text, size=size, bold=bold)
        y -= gap * mm

    def ensure_space(min_y: float = 40 * mm) -> None:
        nonlocal y
        if y < min_y:
            canvas.showPage()
            y = page_h - 20 * mm

    def norm_lines(raw: object) -> list[str]:
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
            return []
        out: list[str] = []
        for item in raw:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out

    def draw_address_column(title: str, lines: list[str], col_x: float, top_y: float) -> float:
        yy = top_y
        draw_str(col_x, yy, title, size=10, bold=True)
        yy -= 5.5 * mm
        canvas.setFont("Helvetica", 9)
        for ln in lines:
            draw_str(col_x, yy, ln, size=9, bold=False)
            yy -= 4 * mm
        return yy

    invoice_type_label = str(payload.get("invoice_type_label") or "Faktura")
    canvas.setTitle(str(payload.get("invoice_number") or f"invoice-{payload.get('id') or 'draft'}"))

    line(invoice_type_label, size=16, bold=True, gap=7)
    line(str(payload.get("document_status_label") or "Doklad"), size=10, bold=False, gap=5)
    inv_no = payload.get("invoice_number")
    line(f"Číslo: {inv_no if inv_no else '(koncept — číslo po vystavení)'}", size=10, gap=5)
    line(f"Stav: {payload.get('status_label') or payload.get('status') or '-'}", size=10, gap=5)

    issue_l = str(payload.get("issue_date_label") or "").strip()
    if issue_l and issue_l != "-":
        line(f"Datum vystavení: {issue_l}", size=10, gap=5)
    else:
        line(f"Datum vystavení: {payload.get('issued_at_label') or '-'}", size=10, gap=5)
    delivery_l = str(payload.get("delivery_date_label") or "").strip()
    if delivery_l and delivery_l != "-":
        line(f"Datum dodání / plnění: {delivery_l}", size=10, gap=5)
    line(f"Splatnost: {payload.get('due_at_label') or '-'}", size=10, gap=5)

    vs = str(payload.get("variable_symbol") or "").strip()
    if vs:
        line(f"Variabilní symbol: {vs}", size=10, gap=5)
    cs = str(payload.get("constant_symbol") or "").strip()
    if cs:
        line(f"Konstantní symbol: {cs}", size=10, gap=5)
    ss = str(payload.get("specific_symbol") or "").strip()
    if ss:
        line(f"Specifický symbol: {ss}", size=10, gap=5)
    if payload.get("order_number"):
        line(f"Objednávka: {payload.get('order_number')}", size=10, gap=5)
    line(f"Způsob úhrady: {payload.get('payment_method') or 'prevod'}", size=10, gap=5)
    if payload.get("issued_by"):
        line(f"Vystavil/a: {payload.get('issued_by')}", size=10, gap=5)

    y -= 2 * mm
    supplier_lines = norm_lines(payload.get("supplier_lines"))
    customer_lines = norm_lines(payload.get("customer_lines"))
    block_top = y
    left_bottom = draw_address_column("Dodavatel", supplier_lines, margin, block_top)
    right_bottom = draw_address_column("Odběratel", customer_lines, mid_x, block_top)
    y = min(left_bottom, right_bottom) - 4 * mm

    veh = str(payload.get("vehicle_label") or "").strip()
    if veh:
        line(f"Vozidlo: {veh}", size=9, gap=5)

    line(f"Měna: {payload.get('currency') or 'CZK'}", size=10, gap=7)

    ensure_space(50 * mm)
    line("Položky", size=11, bold=True, gap=7)

    items = payload.get("lines") or []
    if not isinstance(items, Iterable):
        items = []

    for raw_item in items:
        ensure_space(28 * mm)
        if not isinstance(raw_item, Mapping):
            continue
        desc = str(raw_item.get("description") or "Položka")
        qty = raw_item.get("quantity") or 0
        unit = raw_item.get("unit") or "ks"
        unit_price = raw_item.get("unit_price") or 0
        tax_rate = raw_item.get("tax_rate") or 0
        line_total = raw_item.get("line_total") or 0
        line(desc, size=11, bold=True, gap=5)
        line(
            f"{qty} {unit} × {unit_price} Kč, DPH {tax_rate} % → řádek celkem: {line_total} Kč",
            size=10,
            gap=5,
        )
        y -= 1.5 * mm

    y -= 4 * mm
    ensure_space(35 * mm)
    line(f"Základ: {payload.get('subtotal') or 0} Kč", size=11, bold=False, gap=5)
    line(f"DPH celkem: {payload.get('tax_total') or 0} Kč", size=11, bold=False, gap=5)
    line(f"Celkem k úhradě: {payload.get('total') or 0} Kč", size=13, bold=True, gap=8)

    cust_note = str(payload.get("customer_note_pdf") or "").strip()
    int_note = str(payload.get("internal_note") or "").strip()
    notes_plain = str(payload.get("notes") or "").strip()
    if cust_note:
        line("Poznámka na dokladu:", size=10, bold=True, gap=5)
        line(cust_note, size=9, gap=4)
    elif notes_plain:
        line("Poznámka:", size=10, bold=True, gap=5)
        line(notes_plain, size=9, gap=4)
    if int_note:
        line("Interní poznámka (servis):", size=9, bold=True, gap=4)
        line(int_note, size=8, gap=4)

    line(
        "Doklad vystaven v aplikaci TooZ servis — u konceptu jde o nečíslovaný náhled.",
        size=8,
        gap=5,
    )

    canvas.save()
    return buffer.getvalue()
