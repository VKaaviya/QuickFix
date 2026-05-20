import frappe
from frappe.utils import today


def check_low_stock():
    already_checked = frappe.db.exists(
        "Audit Log",
        {
            "action":    "low_stock_check",
            "timestamp": [">=", today()],
        },   
    )

    if already_checked:
        return

    
    frappe.get_doc({
        "doctype":       "Audit Log",
        "doctype_name":  "Spare Part",
        "document_name": "Daily Low Stock Check",
        "action":        "low_stock_check",
        "user":          "Administrator",      
        "timestamp":     frappe.utils.now(),
    }).insert(ignore_permissions=True)

    parts = frappe.get_all(
        "Spare Part",
        fields=["name", "part_name", "stock_qty", "reorder_level"],
    )

    manager = frappe.db.get_value(
        "Quickfix Settings",
        "Quickfix Settings",
        "manager_email",
    )

    for part in parts:
        if part.stock_qty <= part.reorder_level:
            frappe.get_doc({
                "doctype":       "Notification Log",
                "subject":       f"Low stock alert: {part.part_name}",
                "email_content": (
                    f"Stock for <b>{part.part_name}</b> is low.<br>"
                    f"Current stock: {part.stock_qty} | "
                    f"Reorder level: {part.reorder_level}"
                ),
                "type":          "Alert",
                "document_type": "Spare Part",
                "document_name": part.name,
                "from_user":     "Administrator",
                "for_user":      manager,
            }).insert(ignore_permissions=True)