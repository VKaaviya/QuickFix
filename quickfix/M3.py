import frappe
def logging():
    logger = frappe.logger("quickfix")
    logger.info("Quickfix app logger initialized")
    logger.warning("This is a warning from Quickfix app logger")
    logger.error("This is an error from Quickfix app logger")
    
def run_error_backgroundjob():
    frappe.enqueue(error_job)
def error_job():
    raise Exception("This is a test exception from background job")