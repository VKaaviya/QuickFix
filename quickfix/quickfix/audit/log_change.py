import frappe

def logchange(doc,method):
    if doc.doctype =="Audit Log":
        return
    log=frappe.get_doc({
        "doctype":"Audit Log",
        "doctype_name": doc.doctype,
        "document_name":doc.name,
        "action":method,
        "user":frappe.session.user,
        "timestamp":frappe.utils.now_datetime()
    })
    log.insert(ignore_permissions=True)