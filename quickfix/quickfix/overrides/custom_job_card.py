import frappe
from quickfix.quickfix.doctype.job_card.job_card import JobCard

# Method Resolution Order (MRO) is the order Python uses to search the class
# hierarchy for a method implementation. In multiple inheritance, MRO determines
# which parent method is called first, second, and so on.
#
# In a DocType controller override, calling super() is non-negotiable because the
# parent class may contain essential validation and workflow logic for the
# document. If you skip super().validate(), you bypass that base behavior and
# risk leaving the document in an invalid or inconsistent state.
#
# Use override_doctype_class when you want to replace or extend the full
# controller class for a DocType. This is appropriate when you need class-based
# inheritance, custom methods, and a modified validation/submission lifecycle.
#
# Use doc_events when you only need to attach a standalone callback to an event
# like validate, on_submit, or on_cancel. doc_events is simpler for single
# event handlers, but it does not provide a custom class controller.

class CustomJobCard(JobCard):
    def validate(self):
        super().validate()
        print("Custom validation logic for Job Card")
        self.check_urgent_unassigned()

    def check_urgent_unassigned(self):

        if self.priority == "Urgent" and not self.assigned_technician:
            manager = frappe.db.get_value("Quickfix Settings", None, "manager_email")
            print(manager)
            frappe.enqueue(
                "quickfix.quickfix.overrides.custom_job_card.send_urgent_notification",
                job_card=self.name,
                manager=manager,
            )

def send_urgent_notification(job_card, manager):
    job_card_url = frappe.utils.get_url_to_form("Job Card", job_card)
    frappe.sendmail(
        recipients=[manager],
        subject=f"Urgent Job Card Unassigned: {job_card}",
        message=(
            f"The urgent job card <a href='{job_card_url}'>{job_card}</a> "
            "is currently unassigned. Please assign it as soon as possible."
        ),
        now=True,
    )