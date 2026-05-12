import frappe
from frappe.tests import IntegrationTestCase
import quickfix.monkey_patches
quickfix.monkey_patches.apply_all()
class TestCustomUrlPrefix(IntegrationTestCase):
    """
    Integration tests for custom URL prefix.
    Use this class for testing interactions between multiple components."""
    def test_with_prefix(self):
        frappe.conf.custom_url_prefix = "https://cdn.test.com"

        from frappe.utils import get_url
        url = get_url("/test")

        self.assertEqual(url.startswith("https://cdn.test.com"),True)

    def test_without_prefix(self):
        frappe.conf.custom_url_prefix = ""

        from frappe.utils import get_url
        url = get_url("/test")

        self.assertNotIn("cdn", url)