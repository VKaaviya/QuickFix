import frappe

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

    return frappe.db.count(doctype, filters)


def create_audit_log(doctype_name, action):
    frappe.get_doc({
        "doctype"      : "Audit Log",
        "doctype_name" : doctype_name,
        "action"       : action,
        "user"         : frappe.session.user,
        "timestamp"    : frappe.utils.now_datetime()
    }).insert(ignore_permissions=True)

@frappe.whitelist()
def get_status_chart_data():

    data = frappe.db.sql("""
        SELECT status, COUNT(*) as count
        FROM `tabJob Card`
        GROUP BY status
    """, as_dict=True)

    return {
        "labels": [d.status for d in data],
        "datasets": [
            {
                "name": "Jobs",
                "values": [d.count for d in data]
            }
        ]
    }