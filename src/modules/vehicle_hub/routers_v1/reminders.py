"""
Reminders API v1.0 router (Připomínky)
Kompletní CRUD operace pro automatické i ruční připomínky
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from typing import List
from datetime import date, datetime, timedelta

from ..database import get_db
from ..models import (
    Vehicle as VehicleModel,
    ServiceRecord as ServiceRecordModel,
    Customer,
    Reminder as ReminderModel
)
from .auth import get_current_user
from .schemas import ReminderOutV1, ReminderCreateV1, ReminderUpdateV1
from ..email_notifications import send_reminder_email, send_reminder_created_email
from .reminder_settings import get_reminder_settings
from datetime import date, timedelta

router = APIRouter(prefix="/reminders", tags=["reminders-v1"])


@router.get("", response_model=List[ReminderOutV1])
def get_reminders(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací připomínky pro aktuálního uživatele (automatické i ruční)"""
    try:
        reminders = []
        
        # Načíst všechna vozidla uživatele
        vehicles = db.query(VehicleModel).filter(
            VehicleModel.user_email == current_user.email
        ).all()
        
        today = date.today()
        thirty_days_later = today + timedelta(days=30)
        
        for vehicle in vehicles:
            vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or "Bez názvu"
            
            # 1. STK připomínka
            if vehicle.stk_valid_until:
                if vehicle.stk_valid_until <= thirty_days_later:
                    days_until = (vehicle.stk_valid_until - today).days
                    if days_until < 0:
                        text = f"STK vypršela před {abs(days_until)} dny"
                    elif days_until == 0:
                        text = "STK vyprší dnes"
                    else:
                        text = f"STK vyprší za {days_until} dní"
                    
                    reminders.append(ReminderOutV1(
                        id=None,
                        type="STK",
                        vehicle_id=vehicle.id,
                        vehicle_name=vehicle_name,
                        text=text,
                        due_date=vehicle.stk_valid_until,
                        is_manual=False,
                        is_completed=False
                    ))
            
            # 2. Výměna oleje připomínka
            from sqlalchemy import desc, nullslast
            last_oil_service = db.query(ServiceRecordModel).filter(
                ServiceRecordModel.vehicle_id == vehicle.id,
                ServiceRecordModel.category.isnot(None),
                ServiceRecordModel.category == "OLEJ"
            ).order_by(nullslast(desc(ServiceRecordModel.performed_at))).first()
            
            if last_oil_service and last_oil_service.mileage:
                current_mileage = last_oil_service.mileage
                next_oil_km = current_mileage + 15000
                
                # Najít nejnovější záznam s mileage
                latest_record = db.query(ServiceRecordModel).filter(
                    ServiceRecordModel.vehicle_id == vehicle.id,
                    ServiceRecordModel.mileage.isnot(None)
                ).order_by(nullslast(desc(ServiceRecordModel.performed_at))).first()
                
                if latest_record and latest_record.mileage:
                    current_km = latest_record.mileage
                    km_until_oil = next_oil_km - current_km
                    
                    if km_until_oil <= 5000:
                        reminders.append(ReminderOutV1(
                            id=None,
                            type="OLEJ",
                            vehicle_id=vehicle.id,
                            vehicle_name=vehicle_name,
                            text=f"Výměna oleje za cca {km_until_oil} km (při {current_km} km)",
                            due_date=None,
                            is_manual=False,
                            is_completed=False
                        ))
                
                # Kontrola času (1 rok od poslední výměny)
                if last_oil_service.performed_at:
                    try:
                        if isinstance(last_oil_service.performed_at, datetime):
                            one_year_later = last_oil_service.performed_at.date() + timedelta(days=365)
                        elif isinstance(last_oil_service.performed_at, date):
                            one_year_later = last_oil_service.performed_at + timedelta(days=365)
                        else:
                            continue
                    except (AttributeError, TypeError):
                        continue
                    if one_year_later <= thirty_days_later:
                        days_until = (one_year_later - today).days
                        if days_until < 0:
                            text = f"Výměna oleje byla před {abs(days_until)} dny"
                        else:
                            text = f"Výměna oleje za {days_until} dní (1 rok od poslední)"
                        
                        reminders.append(ReminderOutV1(
                            id=None,
                            type="OLEJ",
                            vehicle_id=vehicle.id,
                            vehicle_name=vehicle_name,
                            text=text,
                            due_date=one_year_later,
                            is_manual=False,
                            is_completed=False
                        ))
            
            # 3. Obecné připomínky (next_service_due_date z servisních záznamů)
            upcoming_services = db.query(ServiceRecordModel).filter(
                ServiceRecordModel.vehicle_id == vehicle.id,
                ServiceRecordModel.next_service_due_date.isnot(None),
                ServiceRecordModel.next_service_due_date <= thirty_days_later
            ).order_by(ServiceRecordModel.next_service_due_date.asc()).all()
            
            for service in upcoming_services:
                days_until = (service.next_service_due_date - today).days
                if days_until < 0:
                    text = f"Plánovaný servis: {service.description} (byl před {abs(days_until)} dny)"
                elif days_until == 0:
                    text = f"Plánovaný servis dnes: {service.description}"
                else:
                    text = f"Plánovaný servis za {days_until} dní: {service.description}"
                
                reminders.append(ReminderOutV1(
                    id=None,
                    type="GENERAL",
                    vehicle_id=vehicle.id,
                    vehicle_name=vehicle_name,
                    text=text,
                    due_date=service.next_service_due_date,
                    is_manual=False,
                    is_completed=False
                ))
        
        # Načíst ruční připomínky uživatele (neukončené)
        manual_reminders = []
        try:
            # Zkontrolovat, zda tabulka Reminder existuje
            try:
                inspector = inspect(db.bind)
                table_names = [table.name for table in inspector.get_table_names()]
                if 'reminders' in table_names:
                    manual_reminders = db.query(ReminderModel).filter(
                        ReminderModel.customer_id == current_user.id,
                        ReminderModel.is_completed == False
                    ).all()
            except (AttributeError, TypeError):
                # Pokud inspect selže, zkusit přímo dotaz
                try:
                    manual_reminders = db.query(ReminderModel).filter(
                        ReminderModel.customer_id == current_user.id,
                        ReminderModel.is_completed == False
                    ).all()
                except Exception:
                    manual_reminders = []
        except Exception as e:
            print(f"[REMINDERS] Warning: Chyba při načítání ručních připomínek: {e}")
            import traceback
            traceback.print_exc()
            manual_reminders = []
        
        # Přidat ruční připomínky do seznamu
        for reminder in manual_reminders:
            vehicle_name = "Obecná připomínka"
            if reminder.vehicle_id:
                vehicle = db.query(VehicleModel).filter(
                    VehicleModel.id == reminder.vehicle_id,
                    VehicleModel.user_email == current_user.email
                ).first()
                if vehicle:
                    vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
            
            reminders.append(ReminderOutV1(
                id=reminder.id,
                type=reminder.type,
                vehicle_id=reminder.vehicle_id,
                vehicle_name=vehicle_name,
                text=reminder.text,
                due_date=reminder.due_date,
                is_manual=True,
                is_completed=reminder.is_completed
            ))
        
        # Seřadit podle due_date (nejbližší první, připomínky bez data na konci)
        try:
            reminders.sort(key=lambda r: (r.due_date if r.due_date else date.max, r.is_manual))
        except Exception as e:
            # Pokud sort selže, pokračovat bez řazení
            print(f"[REMINDERS] Warning: Nepodařilo se seřadit připomínky: {e}")
        
        return reminders
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REMINDERS] Error getting reminders: {e}")
        import traceback
        traceback.print_exc()
        # Vrátit prázdný seznam místo 500 chyby, pokud je to možné
        try:
            return []
        except:
            raise HTTPException(status_code=500, detail=f"Chyba při načítání připomínek: {str(e)}")


@router.post("", response_model=ReminderOutV1)
def create_reminder(
    reminder_data: ReminderCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří novou ruční připomínku"""
    try:
        # Ověřit, že vozidlo patří uživateli (pokud je zadáno)
        if reminder_data.vehicle_id:
            vehicle = db.query(VehicleModel).filter(
                VehicleModel.id == reminder_data.vehicle_id,
                VehicleModel.user_email == current_user.email
            ).first()
            
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno nebo nemáte oprávnění")
        
        # Vytvořit připomínku
        reminder = ReminderModel(
            customer_id=current_user.id,
            vehicle_id=reminder_data.vehicle_id,
            type=reminder_data.type,
            text=reminder_data.text,
            due_date=reminder_data.due_date,
            is_completed=False
        )
        
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        
        # Odeslat email notifikaci při vytvoření připomínky (pokud je to povoleno)
        try:
            settings = get_reminder_settings(current_user)
            notification_settings = settings.get("notification", {})
            notification_method = notification_settings.get("notification_method", "app")
            
            # Odeslat email, pokud je nastaveno "email" nebo "both"
            if notification_method in ["email", "both"]:
                send_reminder_created_email(db, reminder)
        except Exception as e:
            # Nechceme, aby selhalo vytvoření připomínky kvůli chybě při odesílání emailu
            print(f"[REMINDERS] Warning: Nepodařilo se odeslat email při vytvoření připomínky: {e}")
        
        # Vytvořit odpověď
        vehicle_name = "Obecná připomínka"
        if reminder.vehicle_id:
            vehicle = db.query(VehicleModel).filter(VehicleModel.id == reminder.vehicle_id).first()
            if vehicle:
                vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
        
        return ReminderOutV1(
            id=reminder.id,
            type=reminder.type,
            vehicle_id=reminder.vehicle_id,
            vehicle_name=vehicle_name,
            text=reminder.text,
            due_date=reminder.due_date,
            is_manual=True,
            is_completed=reminder.is_completed
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Chyba při vytváření připomínky: {str(e)}"
        print(f"[REMINDERS] Error in create_reminder: {error_detail}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=error_detail)


@router.put("/{reminder_id}", response_model=ReminderOutV1)
def update_reminder(
    reminder_id: int,
    reminder_update: ReminderUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje ruční připomínku"""
    try:
        # Načíst připomínku
        reminder = db.query(ReminderModel).filter(
            ReminderModel.id == reminder_id,
            ReminderModel.customer_id == current_user.id
        ).first()
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena nebo nemáte oprávnění")
        
        # Aktualizovat pouze poskytnutá pole
        if reminder_update.type is not None:
            reminder.type = reminder_update.type
        if reminder_update.vehicle_id is not None:
            # Validace vozidla (pokud je zadáno)
            if reminder_update.vehicle_id != 0:
                vehicle = db.query(VehicleModel).filter(
                    VehicleModel.id == reminder_update.vehicle_id,
                    VehicleModel.user_email == current_user.email
                ).first()
                if not vehicle:
                    raise HTTPException(status_code=404, detail="Vozidlo nenalezeno nebo nemáte oprávnění")
                reminder.vehicle_id = reminder_update.vehicle_id
            else:
                reminder.vehicle_id = None
        elif hasattr(reminder_update, 'vehicle_id') and reminder_update.vehicle_id is None:
            # Explicitně None - odstranit vazbu na vozidlo
            reminder.vehicle_id = None
        if reminder_update.text is not None:
            reminder.text = reminder_update.text
        if reminder_update.due_date is not None:
            reminder.due_date = reminder_update.due_date
        if reminder_update.is_completed is not None:
            reminder.is_completed = reminder_update.is_completed
        
        db.commit()
        db.refresh(reminder)
        
        # Vytvořit odpověď
        vehicle_name = "Obecná připomínka"
        if reminder.vehicle_id:
            vehicle = db.query(VehicleModel).filter(VehicleModel.id == reminder.vehicle_id).first()
            if vehicle:
                vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
        
        return ReminderOutV1(
            id=reminder.id,
            type=reminder.type,
            vehicle_id=reminder.vehicle_id,
            vehicle_name=vehicle_name,
            text=reminder.text,
            due_date=reminder.due_date,
            is_manual=True,
            is_completed=reminder.is_completed
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Chyba při aktualizaci připomínky: {str(e)}"
        print(f"[REMINDERS] Error in update_reminder: {error_detail}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=error_detail)


@router.delete("/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Smaže ruční připomínku"""
    try:
        # Načíst připomínku
        reminder = db.query(ReminderModel).filter(
            ReminderModel.id == reminder_id,
            ReminderModel.customer_id == current_user.id
        ).first()
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena nebo nemáte oprávnění")
        
        db.delete(reminder)
        db.commit()
        
        return {"message": "Připomínka byla smazána"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Chyba při mazání připomínky: {str(e)}"
        print(f"[REMINDERS] Error in delete_reminder: {error_detail}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/check-and-send-notifications")
def check_and_send_reminder_notifications(
    db: Session = Depends(get_db)
):
    """
    Kontroluje připomínky a odesílá upozornění předem podle nastavení uživatelů.
    Tento endpoint by měl být volán pravidelně (např. jednou denně z cron jobu nebo Task Scheduleru).
    """
    try:
        today = date.today()
        sent_count = 0
        error_count = 0
        
        # Načíst všechny aktivní připomínky s due_date
        reminders = db.query(ReminderModel).filter(
            ReminderModel.due_date.isnot(None),
            ReminderModel.is_completed == False
        ).all()
        
        for reminder in reminders:
            try:
                # Načíst uživatele a jeho nastavení
                customer = db.query(Customer).filter(Customer.id == reminder.customer_id).first()
                if not customer or not customer.notify_email:
                    continue
                
                settings = get_reminder_settings(customer)
                notification_settings = settings.get("notification", {})
                notification_method = notification_settings.get("notification_method", "app")
                notify_days_before = notification_settings.get("notify_days_before", 7)
                
                # Zkontrolovat, zda má být odesláno upozornění
                if notification_method not in ["email", "both"]:
                    continue
                
                # Vypočítat dny do termínu
                days_until = (reminder.due_date - today).days
                
                # Odeslat upozornění, pokud je to správný den
                if days_until == notify_days_before:
                    # Zkontrolovat, zda už nebylo odesláno upozornění pro tento den
                    from ..models import EmailNotificationLog
                    existing_log = db.query(EmailNotificationLog).filter(
                        EmailNotificationLog.notification_type == "REMINDER",
                        EmailNotificationLog.related_id == reminder.id,
                        EmailNotificationLog.created_at >= datetime.combine(today, datetime.min.time())
                    ).first()
                    
                    if not existing_log:
                        if send_reminder_email(db, reminder):
                            sent_count += 1
                            print(f"[REMINDERS] Odesláno upozornění pro připomínku ID {reminder.id} (uživatel {customer.email}, {days_until} dní před termínem)")
                        else:
                            error_count += 1
                            print(f"[REMINDERS] Chyba při odesílání upozornění pro připomínku ID {reminder.id}")
                
            except Exception as e:
                error_count += 1
                print(f"[REMINDERS] Chyba při zpracování připomínky ID {reminder.id}: {e}")
                import traceback
                traceback.print_exc()
        
        return {
            "status": "ok",
            "checked_reminders": len(reminders),
            "notifications_sent": sent_count,
            "errors": error_count
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při kontrole připomínek: {str(e)}")
