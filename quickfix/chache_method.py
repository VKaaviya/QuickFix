import frappe


@frappe.whitelist()
def get_status_chart_data():
    key="status_chart_data"

    cached_data=frappe.cache.get_value(key)

    if cached_data:
        return cached_data
    
    data=frappe.get_list(
        "Job Card",
        fields=[
                "status",
                {"COUNT": "name", "as": "count"}
            ],
        group_by="status")
    frappe.cache.set_value(key,data,expires_in_sec=300)
    return data

def clear_status_chart_data(doc,method):
    frappe.cache.delete_value("status_chart_data")
