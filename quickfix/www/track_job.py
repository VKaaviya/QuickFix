
import frappe

def get_context(context):
    job_id=frappe.form_dict.get("job_id")
    if job_id:
        doc=frappe.get_doc("Job Card",job_id)
        context.job=doc
    