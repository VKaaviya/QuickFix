import frappe


def extend_bootinfo(bootinfo):
    settings=frappe.get_single("Quickfix Settings")
    bootinfo.quickfix_shop_name=settings.shop_name or ""
    bootinfo.quickfix_manager_email=settings.manager_email or ""
    
