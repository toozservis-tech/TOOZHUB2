"""Exact public owner revoke/contact routes retain service-directed receipts."""
import pytest
from test_reservation_notification_delivery import booking_flow,inbox
from test_quick_service_booking import flow
from test_service_http_lifecycle import http_flow
from test_reverse_service_notifications import access_request


@pytest.mark.parametrize('approved',[False,True])
def test_contact_disconnect_covers_pending_or_approved_without_repeat(booking_flow,approved):
    f=booking_flow;identity=access_request(f)
    if approved:
        r=f.client.put(f'/api/v1/services/access-requests/{identity}',headers=f.headers['owner'],json={'decision':'approved'})
        assert r.status_code==200,r.text
    path='/api/v1/services/my-contacts/'+str(f.actors['service']['id'])
    result=f.client.delete(path,headers=f.headers['owner']);assert result.status_code==200,result.text
    first=inbox(f,'service');assert len(first)==(2 if approved else 1)
    assert first[0]['title']=='Přístup k vozidlu byl odvolán'
    assert f.client.delete(path,headers=f.headers['owner']).status_code==200
    assert len(inbox(f,'service'))==len(first)
    assert f.client.get(f'/api/v1/vehicles/{f.vehicle_id}/records',headers=f.headers['service']).status_code==403


def test_explicit_vehicle_revoke_does_not_allow_stranger_or_duplicate(booking_flow):
    f=booking_flow;identity=access_request(f)
    assert f.client.put(f'/api/v1/services/access-requests/{identity}',headers=f.headers['owner'],json={'decision':'approved'}).status_code==200
    path=f'/api/v1/services/vehicle-access/{f.actors["service"]["id"]}/{f.vehicle_id}'
    assert f.client.delete(path,headers=f.headers['stranger']).status_code==404
    assert f.client.delete(path,headers=f.headers['service']).status_code==403
    result=f.client.delete(path,headers=f.headers['owner']);assert result.status_code==200 and result.json()['revoked']
    again=f.client.delete(path,headers=f.headers['owner']);assert again.status_code==200 and not again.json()['revoked']
    assert len(inbox(f,'service'))==2
