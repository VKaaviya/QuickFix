
from frappe.tests import IntegrationTestCase
import frappe

class TestCIPipeline(IntegrationTestCase):

    def test_environment_sanity(self):
        devices=frappe.get_all("Device Type",pluck="name")

        self.assertIn("Laptop",devices)
        self.assertIn("Smart Phone",devices)
        self.assertIn("Tablet",devices)

        doc=frappe.get_single("Quickfix Settings")

        self.assertEqual(doc.docstatus,0)
        self.assertNotEqual(doc.manager_email,None)

        roles=frappe.get_all("Role",pluck="name")

        self.assertIn("Test QF Manager",roles)
        meta = frappe.get_meta("Job Card")

        self.assertIsNotNone(meta)

        self.assertEqual(len(meta.fields), 26)