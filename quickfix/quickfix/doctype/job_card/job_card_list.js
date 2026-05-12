frappe.listview_settings["Job Card"] = {

    add_fields:['final_amountc','priority'],
    has_indicator_for_draft: true,

    get_indicator (doc){
        if(doc.status ==="Draft"){
            return[__("Draft"),'blue',"staus,=,Draft"];
        }
        else if(doc.status === "Pending Diagnosis"){
            return[__("Pending Diagnosis"),'orange',"status,=,Pending Diagnosis"];
        }
        else if(doc.status === "Awaiting Customer Approval"){
            return[__("Awaiting Customer Approval"),'green',"status,=,Awaiting Customer Approval"];
        }
        else if(doc.status === "In Repair"){
            return[__("In Repair"),'yellow',"status,=,In Repair"];
        }
        else if(doc.status === "Ready for Delivery"){
            return[__("Ready for Delivery"),'purple',"status,=,Ready for Delivery"];
        }
        else if(doc.status === "Delivered"){
            return[__("Delivered"),'gray',"status,=,Delivered"];
        }
        else if(doc.status === "Cancelled"){
            return[__("Cancelled"),'red',"status,=,Cancelled"];
        }
    },
    formatters:{
        final_amountc(val){
            return format_currency(val).bold();
        },
        priority(val){
            if(val === "Normal"){
                return `<span style="color: blue;">${val}</span>`;
            }
            else if(val=== "High"){
                return `<span style="color: orange;">${val}</span>`;
            }
            else if(val === "Urgent"){
                return `<span style="color: red;">${val}</span>`;
            }
            else{
                return val;
            }
        }
    },
    button: {
    show(doc) {
        return doc.status === "In Repair" && doc.docstatus <= 1;
    },
    get_label() {
    return __('mark as ready for delivery');
    },
    get_description(doc) {
    return __('mark {0} as ready for delivery', [doc.name]);
    },
    action(doc) {
    frappe.db.set_value(
        "Job Card",
        doc.name,
        "status",
        "Ready for Delivery"
    ).then((r) => {
        if (r.exc) {
            frappe.show_alert({
                message: __("Failed to update status"),
                indicator: "red",
            });
        } else {
            frappe.show_alert({
                message: __("Status updated to Ready for Delivery"),
                indicator: "green",
            });
            frappe.listview.refresh();
        }
    });
    }
}
};
   