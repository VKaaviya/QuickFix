
import frappe

from frappe.model.document import bulk_insert
from frappe.utils import flt, nowdate , now_datetime
from werkzeug.exceptions import TooManyRequests, BadRequest, NotFound
import re

@frappe.whitelist()
def share_job_card(job_card_name,user_email):
    doc=frappe.get_doc("Job Card",job_card_name)
    frappe.share.add("Job Card",job_card_name,user_email,read=1)
    return f"Job card Shared Successfully with {user_email}"

@frappe.whitelist()
def manager_only_action():
    frappe.only_for("QF Manager")
    return "You are allowed for this action"

@frappe.whitelist()
def get_job_cards_safe():
    user = frappe.session.user
    roles = frappe.get_roles(user)

    # Permission-aware fetch
    job_cards = frappe.get_list(
        "Job Card",
        fields=[
            "name",
            "customer_name",
            "customer_phone",
            "customer_email",
            "assigned_technician",
            "status"
        ]
    )

    # Strip sensitive data for non-managers
    if "QF Manager" not in roles:
        for jc in job_cards:
            jc.pop("customer_phone", None)
            jc.pop("customer_email", None)

    return job_cards

@frappe.whitelist()
def get_overdue_jobs():
    job_card = frappe.qb.DocType("Job Card")
    overdue_date = frappe.utils.add_days(frappe.utils.nowdate(), -7)

    query = (
        frappe.qb.from_(job_card)
        .select(
            job_card.name,
            job_card.customer_name,
            job_card.assigned_technician,
            job_card.creation,
        )
        .where(job_card.status.isin(["Pending Diagnosis", "In Repair"]))
        .where(job_card.creation < overdue_date)
    )

    return query.run(as_dict=True)




@frappe.whitelist()
def get_counts(doctype, filters=None, debug=False, cache=False):
    frappe.enqueue(
        "quickfix.api.create_audit_log",
        doctype_name = doctype,
        action       = "count_queried"
    )
    if frappe.has_permission(doctype, "read"):
        return frappe.db.count(doctype, filters)

    return 0
        

        


def create_audit_log(doctype_name,action,document_name=None):
    frappe.get_doc({
        "doctype"      : "Audit Log",
        "doctype_name" : doctype_name,
        "action"       : action,
        "user"         : frappe.session.user,
        "document_name": document_name if document_name else "",
        "timestamp"    : frappe.utils.now_datetime()
    }).insert(ignore_permissions=True)




@frappe.whitelist()
def generate_monthly_revenue_report(year=None):
    year = int(year or nowdate()[:4])

    report = []

    for i, month in enumerate(range(1, 13), 1):

        jobs = frappe.get_all(
            "Job Card",

            filters={
                "status": "Delivered",
                "delivery_date": [">=", f"{year}-{month:02d}-01"],
                "delivery_date": ["<", f"{year}-{month:02d}-31"]
            },

            fields=[
                "final_amountc",
                "delivery_date"
            ]
        )

        revenue = 0

        for job in jobs:

            if (
                job.delivery_date.month == month
                and job.delivery_date.year == year
            ):

                revenue += flt(job.final_amountc)

        report.append({
            "month": month,
            "revenue": revenue
        })

        frappe.publish_progress(
            percent=round(i / 12 * 100),

            title="Generating Revenue Report",

            description=f"""
                Processing month {month}...
            """
        )

    return report

@frappe.whitelist()
def fail_background_job():
    frappe.enqueue("quickfix.api.deliberately_fail_job")
    return "Failing job enqueued"


def deliberately_fail_job():
    raise Exception("Intentional background job failure for Task D")

def cancel_old_draft():
    frappe.db.sql("""
        UPDATE `tabJob Card`
        SET status = 'Cancelled' 
        WHERE docstatus = 0 AND       
        creation < DATE_SUB(CURDATE,INTERVAL 30 DAYS) 
        LIMIT 1000
    """)

def insert_bulk_audit_log():
    audit_logs = [
        frappe.get_doc({
            "doctype": "Audit Log",
            "name": frappe.generate_hash(length=10),
            "doctype_name": "Job Card",
            "action": "bulk_insert_test",
            "user": frappe.session.user,
            "timestamp": frappe.utils.now_datetime()
        })
        for _ in range(1000)
    ]

    bulk_insert("Audit Log", audit_logs, commit_chunks=True)
    return len(audit_logs)

@frappe.whitelist()
def get_job_summary():
    job_card=frappe.form_dict.get("job_card")
    job_card_doc=frappe.get_doc("Job Card",job_card)
    if not job_card_doc:
        raise NotFound()
    summary={
        "name": job_card_doc.name,
        "customer_name": job_card_doc.customer_name,
        "assigned_technician": job_card_doc.assigned_technician,
        "status": job_card_doc.status
    }
    return summary

@frappe.whitelist(allow_guest=True)
def get_job_by_phone():
    phone=frappe.form_dict.get("phone")
    if not phone:
        raise BadRequest("Phone  number is required")
    
    phone = re.sub(r"\D", "", phone)

    if not phone or len(phone) > 10:
        raise BadRequest(
            "Phone number must contain maximum 10 digits"
        )
    
    ip=frappe.local.request_ip or "unknown"
    
    minutes=now_datetime().strftime("%Y-%m-%d %H:%M")

    cache_key=f"get_job_phone:{ip}:{minutes}"
    cache_count=frappe.cache().get_value(cache_key) or 0
    count=int(cache_count)
    if count>=10:
        raise TooManyRequests("Rate limit exceeded" )
    frappe.cache().set_value(cache_key,count+1,expires_in_sec=60)
    job_cards=frappe.get_list(
        "Job Card",
        filters={"customer_phone":phone},
        fields=["name","customer_name","assigned_technician","status"],
        as_list=False

    )
    if not job_cards:
        raise NotFound()
    return job_cards
