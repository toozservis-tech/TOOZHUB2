import os
import unittest
from unittest.mock import patch
import httpx
from src.modules.email_client.service import EmailService

class EmailTransport(unittest.TestCase):
    def test_https_delivery_and_safe_provider_errors(self):
        with patch.dict(os.environ,{'RESEND_API_KEY':'test-key','EMAIL_FROM':'Test <noreply@example.com>'}):
            service=EmailService()
        self.assertTrue(service.is_configured())
        with patch('src.modules.email_client.service.httpx.Client') as client:
            post=client.return_value.__enter__.return_value.post
            post.return_value=httpx.Response(200,json={'id':'test'})
            self.assertTrue(service.send_simple_email('user@example.com','Test','Test body'))
            self.assertEqual(post.call_args.args[0],'https://api.resend.com/emails')
            self.assertEqual(post.call_args.kwargs['json']['from'],'Test <noreply@example.com>')
            post.return_value=httpx.Response(403,text='provider details must stay private')
            with self.assertRaisesRegex(RuntimeError,'HTTP 403') as error:
                service.send_simple_email('user@example.com','Test','Test body')
            self.assertNotIn('provider details',str(error.exception))
