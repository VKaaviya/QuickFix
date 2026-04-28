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
        "Job card",
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
    job_card = frappe.qb.DocType("Job card")
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
def transfer_job(from_tech,to_tech):
    try:
        job_card=frappe.db.sql("""
            UPDATE `tabJob card`
            SET assigned_technician=%s
            WHERE assigned_technician=%s
        """,(to_tech,from_tech))
        frappe.db.commit()

    except Exception as e:
        frappe.db.rollback()

        frappe.log_error(title="Job Card Transfer Failed", message=frappe.get_traceback())
        raise