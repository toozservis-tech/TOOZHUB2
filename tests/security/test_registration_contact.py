"""Registration must collect a usable contact before creating an unverified account."""
from test_account_flows import AccountFlows, PASSWORD, REGISTRATION_CONTACT
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.vehicle_hub import referrals as r


class RegistrationContactTests(AccountFlows):
    def payload(self, **extra):
        return {'email': 'contact@example.com', 'password': PASSWORD, **REGISTRATION_CONTACT, **extra}

    def test_registration_company_autofill_is_public_bounded_and_only_company_fields(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from src.server.routers import user_auth
        from src.modules.vehicle_hub.routers_v1 import ares_lookup
        provider = SimpleNamespace(status_code=200, json=lambda: {
            'obchodniJmeno': 'Fixture Autoservis', 'dic': 'CZ12345678',
            'sidlo': {'nazevUlice': 'Testovací', 'cisloDomovni': 12, 'nazevObce': 'Praha', 'psc': 11000},
            'extra_private_field': 'must-not-escape'})
        with patch.object(ares_lookup.requests, 'get', return_value=provider) as fetch:
            response = self.client.get('/user/registration-company?ico=12345678')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['company_name'], 'Fixture Autoservis')
            self.assertEqual(response.json()['house_number'], '12')
            self.assertNotIn('extra_private_field', response.json())
            fetch.assert_called_once_with('https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/12345678', timeout=10)
            self.assertEqual(self.client.get('/user/ares?ico=12345678').status_code, 401)
            for bad in ('123', '１２３４５６７８', 'https://example.com'):
                self.assertEqual(self.client.get('/user/registration-company', params={'ico': bad}).status_code, 422)
            self.assertEqual(fetch.call_count, 1)
        with patch.object(user_auth, 'fetch_public_company', return_value={'ico': '12345678'}):
            statuses = [self.client.get('/user/registration-company?ico=12345678').status_code for _ in range(25)]
            self.assertIn(429, statuses)

    def test_registration_company_outage_does_not_leak_provider_diagnostics(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from src.server.routers import user_auth
        with patch.object(user_auth, 'fetch_public_company', side_effect=HTTPException(503, 'internal diagnostic')):
            result = self.client.get('/user/registration-company?ico=12345678')
            self.assertEqual(result.status_code, 503)
            self.assertNotIn('internal diagnostic', result.text)

    def test_missing_and_blank_contact_fields_do_not_create_or_email_account(self):
        for field in REGISTRATION_CONTACT:
            for value in (None, '', '   '):
                with self.subTest(field=field, value=value):
                    self.mocks[-1].reset_mock()
                    payload = self.payload()
                    if value is None:
                        payload.pop(field)
                    else:
                        payload[field] = value
                    response = self.client.post('/user/register', json=payload)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.mocks[-1].assert_not_called()
        with self.Session() as db:
            self.assertEqual(db.query(Customer).count(), 0)

    def test_full_name_phone_and_postal_code_are_validated(self):
        for extra in ({'name': 'Jan'}, {'name': 'Jan 123'}, {'phone': 'abcd1234567'},
                      {'phone': '+420'}, {'phone': '+420777123456123456'}, {'zip': '1'}):
            with self.subTest(extra=extra):
                response = self.client.post('/user/register', json=self.payload(**extra))
                self.assertEqual(response.status_code, 422, response.text)
        with self.Session() as db:
            self.assertEqual(db.query(Customer).count(), 0)

    def test_full_contact_is_persisted_and_account_requires_email_confirmation(self):
        response = self.client.post('/user/register', json=self.payload(
            name='  Jan   Novák  ', phone='+420 (777) 123-456', street='  Opatovec  ',
            street_number='122', city='Opatovec', zip='568 02'))
        self.assertEqual(response.status_code, 200, response.text)
        account_id = response.json()['user']['id']
        with self.Session() as db:
            customer = db.get(Customer, account_id)
            self.assertEqual(customer.name, 'Jan Novák')
            self.assertEqual(customer.phone, '+420777123456')
            self.assertEqual(customer.street, 'Opatovec')
            self.assertEqual(customer.street_number, '122')
            self.assertEqual(customer.zip, '568 02')
            self.assertIsNone(db.get(EmailVerification, account_id).verified_at)
        headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
        self.assertEqual(self.client.get('/test/protected', headers=headers).status_code, 403)


    def test_referral_persists_through_email_verification_without_inviter_visit(self):
        from src.modules.vehicle_hub import referrals as r
        from src.modules.vehicle_hub.models import Vehicle, VehicleOwnership
        from urllib.parse import parse_qs, urlsplit
        import re
        inviter=self.register('inviter@example.com')
        self.assertEqual(inviter.status_code,200)
        with self.Session() as db:
            owner=db.get(Customer,inviter.json()['user']['id'])
            code=r.code_for(db,owner);db.commit()
        for index in range(3):
            response=self.client.post('/user/register',json=self.payload(email=f'invited-{index}@example.com',referral_code=code))
            self.assertEqual(response.status_code,200,response.text)
            customer_id=response.json()['user']['id']
            message=self.mocks[-1].call_args.args[2]
            urls=re.findall(r'https?://[^\s<>]+',message)
            tokens=[parse_qs(urlsplit(url).fragment).get('token',[None])[0] for url in urls]
            token=next(value for value in tokens if value)
            with self.Session() as db:
                c=db.get(Customer,customer_id)
                v=Vehicle(tenant_id=c.tenant_id,user_email=c.email,vin=f'QA{c.id:015}',nickname='Ukázka')
                db.add(v);db.flush()
                db.add(VehicleOwnership(tenant_id=c.tenant_id,vehicle_id=v.id,customer_id=c.id,ownership_type='owner',is_active=True,is_primary=True));db.commit()
            verified=self.client.post('/user/email-verification/confirm',json={'token':token})
            self.assertEqual(verified.status_code,200,verified.text)
        with self.Session() as db:
            self.assertEqual(db.query(r.Referral).filter(r.Referral.qualified_at.isnot(None)).count(),3)
            self.assertEqual(db.query(r.ReferralReward).count(),1)
        duplicate=self.client.post('/user/register',json=self.payload(email='invited-0@example.com',referral_code=code))
        self.assertEqual(duplicate.status_code,400)

    def test_service_invitation_requires_approval_email_then_completed_job(self):
        from src.modules.vehicle_hub.models import Vehicle, VehicleServiceLink
        from src.modules.vehicle_hub.service_job_models import ServiceJob
        from src.modules.vehicle_hub.routers_v1 import service_jobs, auth
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit
        from uuid import uuid4
        import re
        inviter = self.register('inviter@example.com').json()['user']['id']
        administrator = self.register('admin@example.com').json()['user']['id']
        with self.Session() as db:
            db.get(Customer, administrator).role = 'admin'
            code = r.code_for(db, db.get(Customer, inviter))
            db.commit()
        headers = {'Authorization': 'Bearer ' + self.verified_admin_token(administrator)}
        response = self.client.post('/user/register/service-request', json={
            'email': 'new-service@example.com', 'password': PASSWORD, 'ico': '12345678',
            'service_name': 'Test Service', 'responsible_person': 'Test Person',
            'phone': '+420777123456', 'street': 'Test Street', 'city': 'Praha',
            'zip': '11000', 'registration_purpose': 'Isolated referral test', 'referral_code': code})
        self.assertEqual(response.status_code, 200, response.text)
        rid = response.json()['request_id']
        with self.Session() as db:
            self.assertEqual(db.query(r.Referral).one().service_request_id, rid)
            self.assertEqual(db.query(r.ReferralReward).count(), 0)
        approved = self.client.post(f'/admin-api/service-registration-requests/{rid}/approve',
                                    headers=headers, json={'review_note': 'Isolated test'})
        self.assertEqual(approved.status_code, 200, approved.text)
        service_id = approved.json()['service_customer_id']
        message = self.mocks[-1].call_args.args[2]
        token = next(parse_qs(urlsplit(url).fragment)['token'][0]
                     for url in re.findall(r'https?://[^\s<>]+', message)
                     if 'token' in parse_qs(urlsplit(url).fragment))
        login = self.client.post('/user/login', json={'email': 'new-service@example.com',
                                 'password': PASSWORD, 'expected_role': 'service'})
        self.assertEqual(login.status_code, 200, login.text)
        service_headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        self.assertEqual(self.client.get('/test/protected', headers=service_headers).status_code, 403)
        verified = self.client.post('/user/email-verification/confirm', json={'token': token})
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(self.client.get('/test/protected', headers=service_headers).status_code, 200)
        with self.Session() as db:
            self.assertIsNotNone(db.get(EmailVerification, service_id).verified_at)
            self.assertEqual(db.query(r.ReferralReward).count(), 0)
            service = db.get(Customer, service_id)
            car = Vehicle(tenant_id=service.tenant_id, user_email=service.email,
                          vin='QATESTSERV00000001', nickname='Fixture car')
            db.add(car); db.flush()
            db.add(VehicleServiceLink(tenant_id=service.tenant_id, service_customer_id=service_id,
                owner_customer_id=service_id, vehicle_id=car.id, source_type='pending_owner_registration',
                status='approved', scope_create_service_record=True))
            job = ServiceJob(tenant_id=service.tenant_id, vehicle_id=car.id, service_id=service_id,
                client_id=str(uuid4()), creation_hash='fixture', title='Prepared private test job',
                status='in_progress', workflow_version=0)
            db.add(job); db.commit(); job_id = job.id
        self.client.app.include_router(service_jobs.router, prefix='/api/v1')
        update = {'client_id': str(uuid4()), 'expected_version': 1,
                  'status': 'completed', 'message': 'Test work completed'}
        with patch.object(auth, 'log_user_activity'):
            completed = self.client.post(f'/api/v1/service-jobs/{job_id}/updates',
                                         headers=service_headers, json=update)
            self.assertEqual(completed.status_code, 200, completed.text)
            self.assertFalse(completed.json()['shared_with_owner'])
            replay = self.client.post(f'/api/v1/service-jobs/{job_id}/updates',
                                      headers=service_headers, json=update)
            self.assertEqual(replay.status_code, 200, replay.text)
        with self.Session() as db:
            reward = db.query(r.ReferralReward).one()
            self.assertEqual(reward.customer_id, inviter)
            self.assertEqual(reward.source, 'service')
            self.assertIsNotNone(db.query(r.Referral).one().qualified_at)
