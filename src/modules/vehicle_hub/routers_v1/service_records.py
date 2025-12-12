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
        from datetime import datetime
        
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
        
        # Název souboru
        vehicle_name = vehicle.nickname or vehicle.plate or f"vozidlo_{vehicle_id}"
        safe_name = "".join(c for c in vehicle_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"servisni_zaznamy_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = PDF_DIR / filename
        
        # Vytvořit PDF dokument
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # Vlastní styly
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=12,
            spaceBefore=12
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#334155'),
            spaceAfter=6
        )
        
        note_style = ParagraphStyle(
            'CustomNote',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=12,
            leftIndent=20
        )
        
        # Hlavička - informace o vozidle
        story.append(Paragraph("Historie servisních záznamů", title_style))
        story.append(Spacer(1, 12))
        
        # Tabulka s informacemi o vozidle
        vehicle_data = []
        if vehicle.nickname:
            vehicle_data.append(["Název:", vehicle.nickname])
        if vehicle.brand:
            vehicle_data.append(["Značka:", vehicle.brand])
        if vehicle.model:
            vehicle_data.append(["Model:", vehicle.model])
        if vehicle.year:
            vehicle_data.append(["Rok výroby:", str(vehicle.year)])
        if vehicle.vin:
            vehicle_data.append(["VIN:", vehicle.vin])
        if vehicle.plate:
            vehicle_data.append(["SPZ:", vehicle.plate])
        if vehicle.engine:
            vehicle_data.append(["Motor:", vehicle.engine])
        
        if vehicle_data:
            vehicle_table = Table(vehicle_data, colWidths=[80*mm, 110*mm])
            vehicle_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            story.append(vehicle_table)
            story.append(Spacer(1, 20))
        
        # Seznam záznamů
        story.append(Paragraph("Servisní záznamy", heading_style))
        
        if not records:
            story.append(Paragraph("Zatím nebyly přidány žádné servisní záznamy.", normal_style))
        else:
            # Kategorie mapování
            category_map = {
                'OLEJ': '🛢️ Olej',
                'BRZDY': '🛑 Brzdy',
                'PNEU': '⭕ Pneumatiky',
                'STK': '✅ STK',
                'DIAGNOSTIKA': '🔧 Diagnostika',
                'FILTRY': '🔍 Filtry',
                'CHLADICI': '❄️ Chladicí systém',
                'VYFUK': '💨 Výfuk',
                'OSVETLENI': '💡 Osvětlení',
                'KAROSERIE': '🚗 Karoserie',
                'INTERIER': '🪑 Interiér',
                'ELEKTRIKA': '⚡ Elektrika',
                'KLIMATIZACE': '🌡️ Klimatizace',
                'PREVENTIVNI': '🛡️ Preventivní',
                'OPRAVA': '🔨 Oprava',
                'JINE': '📋 Jiné'
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
                
                # Popis
                description = record.description or 'Bez popisu'
                
                # Informace o záznamu
                record_info = f"<b>{i}. {category_display}</b> - {description}"
                if record.mileage:
                    record_info += f" | Nájezd: {record.mileage:,} km"
                if record.price:
                    record_info += f" | Cena: {record.price:,.0f} Kč"
                record_info += f"<br/><i>Datum: {date_str}</i>"
                
                story.append(Paragraph(record_info, normal_style))
                
                # Poznámka (menším písmem)
                if record.note:
                    story.append(Paragraph(f"<i>Poznámka: {record.note}</i>", note_style))
                else:
                    story.append(Spacer(1, 6))
                
                # Oddělovač (kromě posledního)
                if i < len(records):
                    story.append(Spacer(1, 8))
        
        # Vytvořit PDF
        doc.build(story)
        
        # Vrátit soubor s Content-Disposition headerem
        from fastapi.responses import Response
        
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        return Response(
            content=pdf_content,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
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
