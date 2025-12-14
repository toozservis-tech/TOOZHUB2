"""
Service Records API v1.0 router
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import desc, nullslast

from ..database import get_db
from ..models import ServiceRecord as ServiceRecordModel, Vehicle as VehicleModel
from .auth import get_current_user, can_access_vehicle, get_current_user_id
from .schemas import ServiceRecordCreateV1, ServiceRecordUpdateV1, ServiceRecordOutV1
from ..models import Customer

router = APIRouter(prefix="/vehicles", tags=["service-records-v1"])


@router.post("/{vehicle_id}/records", response_model=ServiceRecordOutV1)
def create_service_record(
    vehicle_id: int,
    record_data: ServiceRecordCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří nový servisní záznam"""
    try:
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Vytvořit záznam
        user_id = current_user.id
        record = ServiceRecordModel(
            vehicle_id=vehicle_id,
            user_id=user_id,
            performed_at=record_data.performed_at,
            mileage=record_data.mileage,
            description=record_data.description,
            price=record_data.price,
            note=record_data.note,
            category=record_data.category,
            attachments=record_data.attachments,
            next_service_due_date=record_data.next_service_due_date
        )
        
        db.add(record)
        db.commit()
        db.refresh(record)
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error creating record for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření servisního záznamu: {str(e)}")


@router.get("/{vehicle_id}/pdf", name="generate_pdf")
def generate_service_records_pdf(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Vygeneruje PDF s historií servisních záznamů pro vozidlo.
    
    PDF obsahuje:
    - Hlavičku s informacemi o vozidle (název, VIN, SPZ, atd.)
    - Seznam všech servisních záznamů
    - Pod každým záznamem poznámku menším písmem
    """
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path
        from datetime import datetime, date
        
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst vozidlo
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        # Načíst všechny záznamy - řadit podle data (nejstarší první pro PDF)
        records = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        ).order_by(nullslast(ServiceRecordModel.performed_at.asc())).all()
        
        # Zkontrolovat, zda je dostupný ReportLab
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import mm
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.enums import TA_LEFT, TA_CENTER
            REPORTLAB_AVAILABLE = True
        except ImportError:
            REPORTLAB_AVAILABLE = False
            raise HTTPException(
                status_code=500,
                detail="Generování PDF není dostupné. ReportLab není nainstalován."
            )
        
        # Vytvořit PDF
        from src.core.config import PDF_DIR
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        
        # Název souboru - zajistit ASCII kompatibilitu
        vehicle_name = vehicle.nickname or vehicle.plate or f"vozidlo_{vehicle_id}"
        # Odstranit diakritiku a speciální znaky pro název souboru
        import unicodedata
        safe_name = unicodedata.normalize('NFKD', str(vehicle_name))
        safe_name = ''.join(c for c in safe_name if not unicodedata.combining(c))
        # Převést na ASCII - odstranit všechny ne-ASCII znaky
        safe_name = safe_name.encode('ascii', 'ignore').decode('ascii')
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]  # Omezit délku
        if not safe_name:  # Pokud by bylo prázdné, použít výchozí
            safe_name = f"vozidlo_{vehicle_id}"
        filename = f"servisni_zaznamy_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = PDF_DIR / filename
        
        # Pomocná funkce pro escape HTML a UTF-8
        def escape_html(text):
            """Escape HTML znaků a zajistí UTF-8 kompatibilitu"""
            if text is None:
                return ""
            text = str(text)
            # Escape HTML znaků
            text = text.replace('&', '&amp;')
            text = text.replace('<', '&lt;')
            text = text.replace('>', '&gt;')
            text = text.replace('"', '&quot;')
            text = text.replace("'", '&#39;')
            return text
        
        # Vytvořit PDF dokument s footerem
        def add_footer(canvas_obj, doc):
            """Přidá footer s datem a číslem stránky"""
            canvas_obj.saveState()
            canvas_obj.setFont('Helvetica', 8)
            canvas_obj.setFillColor(colors.HexColor('#64748b'))
            
            # Datum generování - bez českých znaků pro drawString
            gen_date = datetime.now().strftime('%d.%m.%Y %H:%M')
            footer_text = f"Vygenerovano: {gen_date}"
            canvas_obj.drawString(20*mm, 15*mm, footer_text)
            
            # Číslo stránky
            page_num = canvas_obj.getPageNumber()
            canvas_obj.drawRightString(190*mm, 15*mm, f"Stranka {page_num}")
            
            canvas_obj.restoreState()
        
        # Zajistit, že cesta k PDF je ASCII-safe (pro Windows kompatibilitu)
        pdf_path_str = str(pdf_path)
        try:
            # Zkusit vytvořit PDF s UTF-8 cestou
            doc = SimpleDocTemplate(
                pdf_path_str, 
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=30*mm,
                bottomMargin=25*mm
            )
        except (UnicodeEncodeError, OSError) as e:
            # Pokud selže, použít ASCII-safe cestu
            import tempfile
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', dir=str(PDF_DIR))
            temp_pdf.close()
            pdf_path = Path(temp_pdf.name)
            doc = SimpleDocTemplate(
                str(pdf_path), 
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=30*mm,
                bottomMargin=25*mm
            )
        story = []
        styles = getSampleStyleSheet()
        
        # Profesionální barvy
        primary_color = colors.HexColor('#0f172a')  # Tmavě modrá
        secondary_color = colors.HexColor('#1e40af')  # Modrá
        accent_color = colors.HexColor('#3b82f6')  # Světle modrá
        text_color = colors.HexColor('#1e293b')  # Tmavě šedá
        light_gray = colors.HexColor('#f8fafc')  # Velmi světle šedá
        border_color = colors.HexColor('#e2e8f0')  # Světle šedá
        muted_text = colors.HexColor('#64748b')  # Šedá
        
        # Vlastní styly
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=primary_color,
            spaceAfter=8,
            spaceBefore=0,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=muted_text,
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=primary_color,
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold',
            borderWidth=0,
            borderPadding=0
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=text_color,
            spaceAfter=8,
            leading=14,
            fontName='Helvetica'
        )
        
        note_style = ParagraphStyle(
            'CustomNote',
            parent=styles['Normal'],
            fontSize=9,
            textColor=muted_text,
            spaceAfter=10,
            leftIndent=15,
            leading=12,
            fontName='Helvetica-Oblique'
        )
        
        record_title_style = ParagraphStyle(
            'RecordTitle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=primary_color,
            spaceAfter=4,
            fontName='Helvetica-Bold',
            leading=14
        )
        
        # Hlavička s dekorativním pruhem
        header_table_data = [
            [Paragraph("<b>HISTORIE SERVISNÍCH ZÁZNAMŮ</b>", title_style)]
        ]
        header_table = Table(header_table_data, colWidths=[170*mm])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), secondary_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 24),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 15))
        
        # Tabulka s informacemi o vozidle - profesionální design
        vehicle_data = []
        if vehicle.nickname:
            vehicle_data.append(["Název vozidla", escape_html(vehicle.nickname)])
        if vehicle.brand:
            vehicle_data.append(["Značka", escape_html(vehicle.brand)])
        if vehicle.model:
            vehicle_data.append(["Model", escape_html(vehicle.model)])
        if vehicle.year:
            vehicle_data.append(["Rok výroby", str(vehicle.year)])
        if vehicle.vin:
            vehicle_data.append(["VIN", escape_html(vehicle.vin)])
        if vehicle.plate:
            vehicle_data.append(["SPZ", escape_html(vehicle.plate)])
        if vehicle.engine:
            vehicle_data.append(["Motor", escape_html(vehicle.engine)])
        
        if vehicle_data:
            # Přidat prázdný řádek pro lepší vzhled
            vehicle_table = Table(vehicle_data, colWidths=[60*mm, 110*mm])
            vehicle_table.setStyle(TableStyle([
                # Hlavička (první řádek)
                ('BACKGROUND', (0, 0), (0, -1), light_gray),
                ('TEXTCOLOR', (0, 0), (0, -1), primary_color),
                ('TEXTCOLOR', (1, 0), (1, -1), text_color),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, border_color),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, light_gray]),
            ]))
            story.append(vehicle_table)
            story.append(Spacer(1, 25))
        
        # Souhrn (pokud jsou záznamy)
        if records:
            total_price = sum(r.price or 0 for r in records)
            total_records = len(records)
            summary_data = [
                ["Celkový počet záznamů", str(total_records)],
                ["Celková cena servisů", f"{total_price:,.0f} Kč" if total_price > 0 else "Nezadáno"]
            ]
            summary_table = Table(summary_data, colWidths=[100*mm, 70*mm])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), accent_color),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 20))
        
        # Seznam záznamů
        story.append(Paragraph("SERVISNÍ ZÁZNAMY", heading_style))
        
        if not records:
            empty_style = ParagraphStyle(
                'EmptyStyle',
                parent=styles['Normal'],
                fontSize=11,
                textColor=muted_text,
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName='Helvetica-Oblique'
            )
            story.append(Paragraph("Zatím nebyly přidány žádné servisní záznamy.", empty_style))
        else:
            # Kategorie mapování (bez emoji pro lepší kompatibilitu)
            category_map = {
                'OLEJ': 'Olej',
                'BRZDY': 'Brzdy',
                'PNEU': 'Pneumatiky',
                'STK': 'STK',
                'DIAGNOSTIKA': 'Diagnostika',
                'FILTRY': 'Filtry',
                'CHLADICI': 'Chladicí systém',
                'VYFUK': 'Výfuk',
                'OSVETLENI': 'Osvětlení',
                'KAROSERIE': 'Karoserie',
                'INTERIER': 'Interiér',
                'ELEKTRIKA': 'Elektrika',
                'KLIMATIZACE': 'Klimatizace',
                'PREVENTIVNI': 'Preventivní',
                'OPRAVA': 'Oprava',
                'JINE': 'Jiné'
            }
            
            for i, record in enumerate(records, 1):
                # Datum
                if record.performed_at:
                    try:
                        if isinstance(record.performed_at, datetime):
                            date_str = record.performed_at.strftime('%d.%m.%Y %H:%M')
                        elif isinstance(record.performed_at, date):
                            date_str = record.performed_at.strftime('%d.%m.%Y')
                        else:
                            date_str = str(record.performed_at)
                    except (AttributeError, TypeError):
                        date_str = 'Nezadáno'
                else:
                    date_str = 'Nezadáno'
                
                # Kategorie
                category_display = category_map.get(record.category, record.category or 'Jiné')
                
                # Popis - escape HTML pro UTF-8
                description = escape_html(record.description or 'Bez popisu')
                
                # Hlavní řádek záznamu
                record_title = f"<b>{i}. {escape_html(category_display)}</b>"
                story.append(Paragraph(record_title, record_title_style))
                
                # Popis
                story.append(Paragraph(description, normal_style))
                
                # Detaily v tabulce
                details_data = []
                if record.mileage:
                    details_data.append(["Nájezd", f"{record.mileage:,} km"])
                if record.price:
                    details_data.append(["Cena", f"{record.price:,.0f} Kč"])
                details_data.append(["Datum", escape_html(date_str)])
                
                if details_data:
                    details_table = Table(details_data, colWidths=[40*mm, 130*mm])
                    details_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), light_gray),
                        ('TEXTCOLOR', (0, 0), (0, -1), muted_text),
                        ('TEXTCOLOR', (1, 0), (1, -1), text_color),
                        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
                        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('LEFTPADDING', (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
                    ]))
                    story.append(details_table)
                
                # Poznámka (pokud existuje) - escape HTML
                if record.note:
                    note_text = escape_html(record.note)
                    story.append(Paragraph(f"Poznámka: {note_text}", note_style))
                
                # Oddělovač (kromě posledního)
                if i < len(records):
                    story.append(Spacer(1, 12))
        
        # Vytvořit PDF s footerem
        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
        
        # Vrátit soubor s Content-Disposition headerem
        from fastapi.responses import Response
        from urllib.parse import quote
        
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        # Kódovat název souboru pro Content-Disposition header (RFC 5987)
        # Použít ASCII-safe název a UTF-8 encoded verzi
        safe_filename_ascii = filename.encode('ascii', 'ignore').decode('ascii')
        safe_filename_utf8 = quote(filename, safe='')
        
        # Content-Disposition s podporou UTF-8 (RFC 5987)
        content_disposition = f'attachment; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'
        
        return Response(
            content=pdf_content,
            media_type='application/pdf',
            headers={
                'Content-Disposition': content_disposition
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error generating PDF for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při generování PDF: {str(e)}")


@router.get("/{vehicle_id}/records", response_model=List[ServiceRecordOutV1])
def get_service_records(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací všechny servisní záznamy pro vozidlo"""
    try:
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst záznamy - řadit podle performed_at (nejnovější první)
        records = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        ).order_by(nullslast(desc(ServiceRecordModel.performed_at))).all()
        
        return records
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error getting records for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisních záznamů: {str(e)}")


@router.get("/{vehicle_id}/records/{record_id}", response_model=ServiceRecordOutV1)
def get_service_record(
    vehicle_id: int,
    record_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní servisní záznam"""
    try:
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error getting record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisního záznamu: {str(e)}")


@router.put("/{vehicle_id}/records/{record_id}", response_model=ServiceRecordOutV1)
def update_service_record(
    vehicle_id: int,
    record_id: int,
    record_data: ServiceRecordUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Aktualizuje servisní záznam.
    POZOR: Záznamy vytvořené AI asistentem (created_by_ai=True) nelze smazat, pouze upravit.
    """
    try:
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        
        # Aktualizace polí
        if record_data.performed_at is not None:
            record.performed_at = record_data.performed_at
        if record_data.mileage is not None:
            record.mileage = record_data.mileage
        if record_data.description is not None:
            record.description = record_data.description
        if record_data.price is not None:
            record.price = record_data.price
        if record_data.note is not None:
            record.note = record_data.note
        if record_data.category is not None:
            record.category = record_data.category
        if record_data.attachments is not None:
            record.attachments = record_data.attachments
        if record_data.next_service_due_date is not None:
            record.next_service_due_date = record_data.next_service_due_date
        
        db.commit()
        db.refresh(record)
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error updating record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při aktualizaci servisního záznamu: {str(e)}")


@router.delete("/{vehicle_id}/records/{record_id}")
def delete_service_record(
    vehicle_id: int,
    record_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Smaže servisní záznam.
    POZOR: Záznamy vytvořené AI asistentem (created_by_ai=True) nelze smazat.
    """
    try:
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()

        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        
        # Zakázat mazání záznamů vytvořených AI asistentem
        if record.created_by_ai:
            raise HTTPException(
                status_code=403,
                detail="Záznam vytvořený AI asistentem nelze smazat. Můžete ho pouze upravit."
            )

        db.delete(record)
        db.commit()
        
        return {"message": "Servisní záznam byl smazán"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error deleting record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání servisního záznamu: {str(e)}")
