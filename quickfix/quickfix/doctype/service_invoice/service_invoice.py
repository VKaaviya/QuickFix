# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ServiceInvoice(Document):
    def has_permission(self,doc, user):
        if not user:
            user = frappe.session.user

        if "QF Manager" in frappe.get_roles(user):
            return True
        status=frappe.db.get_value("Job Card",self.job_card,"payment_status")
        if status != "Paid":
            return False
        return True
            

