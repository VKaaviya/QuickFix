import frappe
def log_login(login_manager=None):
        if login_manager.user !="Guest":
            doc=frappe.get_doc({
                "doctype":"Audit Log",
                "doctype_name":"User",
                "document_name":login_manager.user,
                "action":"Login",
                "user":login_manager.user,
                "timestamp":frappe.utils.now_datetime()
            })
            doc.insert(ignore_permissions=True)
def logout_log(login_manager=None):
         if login_manager.user !="Guest":
            doc=frappe.get_doc({
                "doctype":"Audit Log",
                "doctype_name":"User",
                "document_name":login_manager.user,
                "action":"Logout",
                "user":login_manager.user,
                "timestamp":frappe.utils.now_datetime()
            })
            doc.insert(ignore_permissions=True)