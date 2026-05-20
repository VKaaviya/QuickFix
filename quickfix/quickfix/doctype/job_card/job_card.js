// Copyright (c) 2026, Kaviya and contributors

let show_reject_dialog = function (frm) {

    const dialog = new frappe.ui.Dialog({
        title : __("Reject Job Card"),
        size  : "small",
        fields: [
            {
                fieldname   : "rejection_reason",
                fieldtype   : "Small Text",
                label       : "Rejection Reason",
                reqd        : 1,
                description : "Please provide a clear reason for rejection."
            },
            {
                fieldname : "notify_customer",
                fieldtype : "Check",
                label     : "Notify Customer via Email",
                default   : 1
            }
        ],
        primary_action_label: __("Confirm Reject"),
        primary_action(values) {
            frappe.call({
                method  : "quickfix.quickfix.doctype.job_card.job_card.reject_job_card",
                args    : {
                    job_card_name    : frm.doc.name,
                    rejection_reason : values.rejection_reason,
                    notify_customer  : values.notify_customer
                },
                freeze         : true,
                freeze_message : __("Rejecting job card..."),
                callback(r) {
                    if (!r.exc) {
                        frappe.show_alert({
                            message  : __("Job Card rejected successfully."),
                            indicator: "red"
                        }, 4);
                        dialog.hide();
                        frm.reload_doc();
                    }
                }
            });
        }
    });

    dialog.show();
};


let transfer_technician = function (frm) {

    frappe.prompt(
        [
            {
                fieldname  : "new_technician",
                fieldtype  : "Link",
                label      : "New Technician",
                options    : "Technician",
                reqd       : 1,
                description: "Select technician to transfer this job to.",
                get_query  : () => {
                    return {
                        filters: { "status": "Active","specilization" :frm.doc.device_type}
                    };
                }
            }
        ],

        function (values) {
            const new_tech = values.new_technician;
            const old_tech = frm.doc.assigned_technician || "Unassigned";

            frappe.confirm(
                `Transfer job from <b>${old_tech}</b>
                 to <b>${new_tech}</b>?
                 <br><br>This will notify the new technician.`,

                function () {
                    frappe.call({
                        method  : "quickfix.quickfix.doctype.job_card.job_card.transfer_technician",
                        args    : {
                            job_card_name  : frm.doc.name,
                            new_technician : new_tech
                        },
                        freeze         : true,
                        freeze_message : "Transferring technician...",
                        callback(r) {
                            if (!r.exc) {
                                frappe.show_alert({
                                    message  : `Transferred to ${new_tech}`,
                                    indicator: "green"
                                }, 4);

                                frm.reload_doc().then(() => {
                                    frm.trigger("assigned_technician");
                                });
                            }
                        }
                    });
                },

                function () {
                    frappe.show_alert({
                        message  : "Transfer cancelled.",
                        indicator: "orange"
                    }, 3);
                }
            );
        },
        __("Transfer Technician"),
        __("Proceed")
    );
};


frappe.ui.form.on("Job Card", {

    setup(frm) {

        frm.set_query("assigned_technician", () => {
            return {
                filters: {
                    "status"     : "Active",
                    "specilization": frm.doc.device_type
                }
            };
        });
    },

    onload(frm) {

    if (frm.job_ready_listener_added) {
        return;
    }

    frm.job_ready_listener_added = true;

    frappe.realtime.on("job_ready", (data) => {

        if (data.job_card === frm.doc.name) {

            frappe.show_alert({
                message: __("Job is Ready for Delivery"),
                indicator: "green"
            });

        }
    });
},

    refresh(frm) {

        if (frm.doc.status) {
            let color = "blue";

            const status_colors = {
                "Pending Diagnosis"          : "orange",
                "In Repair"                  : "yellow",
                "Awaiting Customer Approval" : "green",
                "Ready for Delivery"         : "purple",
                "Delivered"                  : "gray",
                "Cancelled"                  : "red",
            };

            color = status_colors[frm.doc.status] || "blue";
            frm.dashboard.add_indicator(frm.doc.status, color);
        }
        // let color="blue"
	    // if(frm.doc.device_type==="Laptop"){
	    //     color="blue";
	    // }
	    // else if(frm.doc.device_type === "Smart Phone"){
	    //     color="green";
	    // }
	    // else if(frm.doc.device_type==="Tablet"){
	    //     color="orange";
	    // }
	    // frm.dashboard.add_indicator(frm.doc.device_type,color);

        if (frappe.boot.quickfix_shop_name) {
            frm.dashboard.set_headline(
                `Shop: ${frappe.boot.quickfix_shop_name}`
            );
        }
 
        if (
            frm.doc.status    === "Ready for Delivery" &&
            frm.doc.docstatus === 1
        ) {
            frm.add_custom_button("Mark as Delivered", () => {

                frappe.confirm(
                    "Mark this job as Delivered?",

                    function () {
                        frm.set_value("status", "Delivered").then(() => {
                            frm.save();
                        });
                    }
                );
            });
        }


        if (frm.doc.docstatus === 0) {
            frm.add_custom_button("Reject Job", function () {
                show_reject_dialog(frm);
            }, "Actions");
        }

        // Transfer Technician — Draft or Submitted
        if (
            frm.doc.docstatus <= 1 &&
            frm.doc.status !== "Delivered" &&
            frm.doc.status !== "Cancelled"
        ) {
            frm.add_custom_button("Transfer Technician", function () {
                transfer_technician(frm);
            },"Actions");
        }
    },

    assigned_technician(frm) {

        if (!frm.doc.assigned_technician || !frm.doc.device_type) {
            return;
        }

        frappe.db.get_value(
            "Technician",
            frm.doc.assigned_technician,
            "specilization"
        ).then((r) => {
            if (!r.message) return;

            const specialization = r.message.specilization;

            if (specialization !== frm.doc.device_type) {
                 frappe.throw(
                        `Selected technician specializes in
                        <b>${specialization}</b>, but device
                        type is <b>${frm.doc.device_type}</b>.
                        Please select a technician with the correct specialization.`,
                    );
            }
        });

        frappe.show_alert({
            message  : `Technician set to ${frm.doc.assigned_technician}`,
            indicator: "green"
        }, 3);
    },
});


frappe.ui.form.on("Part Item", {

    quantity(frm, cdt, cdn) {
        let row   = locals[cdt][cdn];
        let total = (row.quantity || 0) * (row.unit_price || 0);

        frappe.model.set_value(cdt, cdn, "total_price", total);
    },

    unit_price(frm, cdt, cdn) {
        let row   = locals[cdt][cdn];
        let total = (row.quantity || 0) * (row.unit_price || 0);

        frappe.model.set_value(cdt, cdn, "total_price", total);
    }
});