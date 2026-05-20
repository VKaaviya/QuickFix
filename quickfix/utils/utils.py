import frappe
import base64
import pyqrcode

from io import BytesIO

def get_shop_name():
    doc=frappe.get_single("Quickfix Settings")
    return doc.shop_name


def format_job_id(id):
    return "JOB#"+id




def get_qr_code(name):

    url = frappe.utils.get_url(
        f"/app/job-card/{name}"
    )

    qr = pyqrcode.create(url)

    buffer = BytesIO()

    qr.png(buffer, scale=5)

    img = base64.b64encode(
        buffer.getvalue()
    ).decode()

    return f"data:image/png;base64,{img}"