import json

import frappe
import hashlib
from frappe.utils import now
import requests
import hmac
from werkzeug.exceptions import  BadRequest, NotFound
from quickfix.api import create_audit_log
from quickfix.signature import generate_signature


def job_card_submitted(doc, method=None):

    webhook_id = hashlib.sha256(
        f"{doc.name}-job_submitted-{now()}".encode()
    ).hexdigest()

    frappe.enqueue(
        "quickfix.webhooks.send_webhook",
        queue="short",
        job_card_name=doc.name,
        webhook_id=webhook_id
    )




def send_webhook(job_card_name, webhook_id, retry_count=0):

    settings = frappe.get_single("Quickfix Settings")

    if not settings.webhook_url:
        return

    # Deduplication check
    already_sent = frappe.db.exists(
        "Audit Log",
        {
            "name": webhook_id,
            "action":"Webhook Success",
            "document_name": job_card_name,
        }
    )

    if already_sent:
        return

    doc = frappe.get_doc("Job Card", job_card_name)

    payload = {
        "event": "job_submitted",
        "job_card": doc.name,
        "customer": doc.customer_name,
        "amount": doc.final_amountc
    }

    response = requests.get(
        settings.webhook_url,
        json=payload,
        timeout=5
    )
    response.raise_for_status()
    frappe.get_doc({
        "doctype": "Audit Log",
        "name": webhook_id,
        "action": "Webhook Success",
        "doctype_name": "Job Card",
        "document_name": doc.name,
        "timestamp": now(),
    }).insert(ignore_permissions=True)





@frappe.whitelist(allow_guest=True)
def payment_webhook():

    payload = frappe.request.data

    secret = frappe.conf.get("secret")

    signature = frappe.get_request_header("X-Signature")

    if not signature or not secret:
        frappe.throw("Unauthorized")

    expected_signature = generate_signature(payload, secret)

    if not hmac.compare_digest(signature, expected_signature):
        raise BadRequest("Authorization failed")

    data = json.loads(payload.decode())

    reference = data.get("ref")

    audit = frappe.get_value(
        "Audit Log",
        filters={
            "document_name": reference,
            "action": "Payment Received"
        }
    )

    if audit:
        return {
            "status": "duplicate",
            "message": "Webhook already processed"
        }

    if not frappe.db.exists("Job Card", reference):
        raise NotFound("Job Card not found")

    frappe.db.set_value("Job Card", reference, "payment_status", "Paid")

    doc = frappe.get_doc("Job Card", reference)

    create_audit_log(
        doctype_name = "Job Card",
        action       = "Payment Received",
        document_name= doc.name
    )

    return {
        "status": "ok"
    }
