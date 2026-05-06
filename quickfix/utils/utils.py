import frappe

def get_shop_name():
    doc=frappe.get_single("Quickfix Settings")
    return doc.shop_name


def format_job_id(id):
    return "JOB#"+id