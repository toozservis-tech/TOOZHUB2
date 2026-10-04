"""Provider payload and SMTP reply routing, with no external mail/network."""
from email import message_from_string
import json

import httpx
import pytest

from src.modules.email_client import service as mail


def test_resend_support_message_has_authenticated_reply_address(monkeypatch):
    captured = []
    def deliver(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'id':'synthetic-only'})
    original = httpx.Client
    monkeypatch.setattr(mail.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(deliver), **kw))
    monkeypatch.setenv('EMAIL_FROM', 'SprávaVozidel <support@example.com>')
    monkeypatch.setenv('RESEND_API_KEY', 'synthetic-not-a-real-key')
    sender = mail.EmailService(host='', username='', password='', from_email='')
    assert sender.from_email == 'Evidence Vozidel <support@example.com>'
    assert sender.is_configured()
    assert sender.send_simple_email(to='support@example.com', subject='Synthetic support',
        body='Synthetic request', html_body='<p>Synthetic request</p>', reply_to='user@example.com')
    assert captured[0]['to'] == ['support@example.com'] and captured[0]['reply_to'] == 'user@example.com'


def test_smtp_support_message_has_reply_to_header(monkeypatch):
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def sendmail(self, sender, recipients, content): sent.append(message_from_string(content))
    monkeypatch.setenv('EMAIL_FROM', 'support@example.com')
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.setattr(mail.smtplib, 'SMTP_SSL', SMTP)
    sender = mail.EmailService(host='smtp.example.com', port=465, username='fixture', password='fixture')
    assert sender.send_simple_email(to='support@example.com', subject='Synthetic support',
        body='Synthetic request', html_body='<p>Synthetic request</p>', reply_to='user@example.com')
    assert sent[0]['Reply-To'] == 'user@example.com'
