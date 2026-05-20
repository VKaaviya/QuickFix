
import frappe

def get_context(context):
    job_id=frappe.form_dict.get("job_id")

    if job_id:
        jobs = frappe.get_list("Job Card",filters={"name": job_id},fields=["name","customer_name","status","assigned_technician"])

        if jobs:
            context.jobs=jobs
        else:
            context.error="Job Card not found"
    
    context.title="Track My Job"
    context.description="Track the status of your repair job with Quickfix. Enter your Job ID to see real-time updates on the progress of your repair, including current status, estimated completion time, and any notes from our technicians. Stay informed every step of the way with Quickfix's Job Tracking."
    context.og_title="Track My Job - Quickfix"
    



    