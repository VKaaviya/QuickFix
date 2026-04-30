# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

def has_permission(doc,permtype="read", *,user=None):
        if doc.flags.ignore_permissions:
            return True

        if not user:
            user = frappe.session.user

        if "QF Manager" in frappe.get_roles(user):
            return True

        if permtype == "create":
            return True

        status = frappe.db.get_value("Job Card", doc.job_card, "payment_status")
        return status == "Paid"
class ServiceInvoice(Document):
    pass

