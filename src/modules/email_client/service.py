"""
Email Client Service - služba pro odesílání emailů
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List
from pathlib import Path
from dataclasses import dataclass

from src.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM


@dataclass
class EmailMessage:
    """Reprezentace emailové zprávy"""
    to: List[str]
    subject: str
    body: str
    html_body: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    attachments: Optional[List[Path]] = None


class EmailService:
    """Služba pro odesílání emailů"""
    
    def __init__(
        self,
        host: str = SMTP_HOST,
        port: int = SMTP_PORT,
        username: str = SMTP_USER,
        password: str = SMTP_PASSWORD,
        from_email: str = SMTP_FROM
    ):
        self.host = host
        self.port = port
        self.username = username.strip() if username else None
        # Vyčistit heslo - odstranit jen bílé znaky a uvozovky (středník je součástí hesla)
        if password:
            self.password = password.strip().strip('"').strip("'")
        else:
            self.password = None
        self.from_email = from_email
    
    def is_configured(self) -> bool:
        """Zkontroluje, zda je email správně nakonfigurován"""
        return bool(self.username and self.password and self.host)
    
    def send_email(self, message: EmailMessage) -> bool:
        """
        Odešle email.
        
        Args:
            message: EmailMessage objekt s daty emailu
            
        Returns:
            True pokud email byl úspěšně odeslán
            
        Raises:
            ValueError: Pokud nejsou nakonfigurovány SMTP údaje
            smtplib.SMTPException: Při chybě odesílání
        """
        if not self.is_configured():
            raise ValueError("Email není nakonfigurován. Nastavte SMTP údaje v konfiguraci.")
        
        # Vytvořit zprávu
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_email
        msg["To"] = ", ".join(message.to)
        msg["Subject"] = message.subject
        
        if message.cc:
            msg["Cc"] = ", ".join(message.cc)
        
        # Přidat text body
        msg.attach(MIMEText(message.body, "plain", "utf-8"))
        
        # Přidat HTML body (pokud existuje)
        if message.html_body:
            msg.attach(MIMEText(message.html_body, "html", "utf-8"))
        
        # Přidat přílohy
        if message.attachments:
            for attachment_path in message.attachments:
                self._add_attachment(msg, attachment_path)
        
        # Seznam všech příjemců
        all_recipients = list(message.to)
        if message.cc:
            all_recipients.extend(message.cc)
        if message.bcc:
            all_recipients.extend(message.bcc)
        
        # Odeslat email
        try:
            # Port 465 vyžaduje SSL (SMTP_SSL), port 587 vyžaduje STARTTLS
            if self.port == 465:
                # SSL připojení pro port 465
                with smtplib.SMTP_SSL(self.host, self.port, timeout=10) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
            else:
                # STARTTLS pro port 587 a ostatní
                with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                    server.starttls()
                    server.login(self.username, self.password)
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
            return True
        except smtplib.SMTPException as e:
            print(f"[EMAIL] Chyba při odesílání emailu: {e}")
            raise
    
    def _add_attachment(self, msg: MIMEMultipart, file_path: Path) -> None:
        """Přidá přílohu k emailu"""
        if not file_path.exists():
            print(f"[EMAIL] Příloha neexistuje: {file_path}")
            return
        
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={file_path.name}"
        )
        msg.attach(part)
    
    def send_simple_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Zjednodušené odeslání emailu.
        
        Args:
            to: Email příjemce
            subject: Předmět emailu
            body: Text emailu
            html_body: HTML verze emailu (volitelné)
            
        Returns:
            True pokud byl email úspěšně odeslán
        """
        message = EmailMessage(
            to=[to],
            subject=subject,
            body=body,
            html_body=html_body
        )
        return self.send_email(message)
    
    def send_vehicle_reminder(
        self,
        to: str,
        vehicle_name: str,
        reminder_type: str,
        due_date: str
    ) -> bool:
        """
        Odešle připomínku ohledně vozidla (STK, pojištění, servis atd.)
        
        Args:
            to: Email příjemce
            vehicle_name: Název vozidla
            reminder_type: Typ připomínky (STK, pojištění, servis)
            due_date: Datum expirace
            
        Returns:
            True pokud byl email úspěšně odeslán
        """
        subject = f"Připomínka: {reminder_type} - {vehicle_name}"
        
        body = f"""Dobrý den,

připomínáme Vám blížící se termín pro Vaše vozidlo {vehicle_name}:

Typ: {reminder_type}
Datum: {due_date}

S pozdravem,
TooZ Hub 2
"""
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
        .reminder-box {{ background: white; padding: 15px; border-radius: 6px; 
                        border-left: 4px solid #667eea; margin: 15px 0; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚗 TooZ Hub 2</h1>
            <p>Připomínka pro Vaše vozidlo</p>
        </div>
        <div class="content">
            <p>Dobrý den,</p>
            <p>připomínáme Vám blížící se termín pro Vaše vozidlo:</p>
            
            <div class="reminder-box">
                <strong>Vozidlo:</strong> {vehicle_name}<br>
                <strong>Typ:</strong> {reminder_type}<br>
                <strong>Datum:</strong> {due_date}
            </div>
            
            <p>Nezapomeňte včas zajistit potřebné úkony.</p>
            
            <div class="footer">
                <p>S pozdravem,<br>TooZ Hub 2</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        return self.send_simple_email(to, subject, body, html_body)
