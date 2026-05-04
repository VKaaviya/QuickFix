

import frappe


def after_install():
    default_device_types = ["Laptop", "Smart Phone", "Tablet"]
    created_device_types = []

    for device_type in default_device_types:
        if not frappe.db.exists("Device Type", {"device_type": device_type}):
            frappe.get_doc(
                {
                    "doctype": "Device Type",
                    "device_type": device_type,
                }
            ).insert(ignore_permissions=True)
            created_device_types.append(device_type)

    settings_created = False
    if not frappe.db.exists("Quickfix Settings"):
        frappe.get_doc(
            {
                "doctype": "Quickfix Settings",
                "shop_name": "Quickfix Service Center",
                "manager_email": "manager@example.com",
                "default_labour_charge": 500,
                "low_stock_alert_enabled": 1,
            }
        ).insert(ignore_permissions=True)
        settings_created = True

    message = "Quickfix setup completed successfully."
    if created_device_types:
        message += f" Created Device Types: {', '.join(created_device_types)}."
    if settings_created:
        message += " Created default Quickfix Settings."

    frappe.msgprint(message)



