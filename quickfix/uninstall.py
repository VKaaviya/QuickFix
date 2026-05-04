import frappe

def before_uninstall():
    docs = frappe.get_list(
        "Job Card",
        filters={"docstatus": 1},
        fields=["name"]
    )

    if docs:
        names = ", ".join([d["name"] for d in docs])
        frappe.throw(f"Cannot uninstall: Submitted Job Cards exist → {names}")