"""Admin access and isolation are enforced by the server, not by navigation."""
from test_account_flows import AccountFlows
from src.modules.vehicle_hub.models import Customer
from src.core.rbac import vehicle_read_policy, vehicle_write_policy

class AdminRoles(AccountFlows):
    def test_control_center_read_and_write_by_role(self):
        account=self.register().json()
        headers={'Authorization':'Bearer '+self.verified_admin_token(account['user']['id'])}
        for role in ['user','service','admin','developer_admin']:
            with self.Session() as db:
                user=db.get(Customer,account['user']['id']);user.role=role;db.commit()
            expected=200 if role in {'admin','developer_admin'} else 403
            response=self.client.get('/admin-api/control-center/capabilities',headers=headers)
            self.assertEqual(response.status_code,expected,(role,response.text))
            response=self.client.post('/admin-api/control-center/users/999999/force-logout',json={'reason':'Isolated permission test'},headers=headers)
            self.assertEqual(response.status_code,404 if expected==200 else 403,(role,response.text))
    def test_vehicle_ownership_and_service_links(self):
        self.assertFalse(vehicle_read_policy(role='user',is_owner=False,has_service_access=False).allowed)
        self.assertFalse(vehicle_read_policy(role='service',is_owner=False,has_service_access=False).allowed)
        self.assertTrue(vehicle_read_policy(role='service',is_owner=False,has_service_access=True).allowed)
        self.assertFalse(vehicle_write_policy(role='service',is_owner=False).allowed)
        for role in ['admin','developer_admin']:
            self.assertTrue(vehicle_read_policy(role=role,is_owner=False,has_service_access=False).allowed)
            self.assertTrue(vehicle_write_policy(role=role,is_owner=False).allowed)
