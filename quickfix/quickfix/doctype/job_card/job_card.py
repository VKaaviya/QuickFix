# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document
from frappe.utils import flt

def get_permission_query_conditions(user):
	if not user:
		user = frappe.session.user
	if "QF technician" in frappe.get_roles(user):
		return """(`tabJob Card`.assigned_technician = '{user}')""".format(user=user)
	return ""

class Jobcard(Document):
	def validate(self):
		self.validate_customer_phone()
		self.validate_assigned_technician()
		self.calculate_parts_total()
		self.set_labour_charge()
		self.set_final_amount()

	def before_submit(self):
		if self.status != "Ready for Delivery":
			frappe.throw("Job card can only be submitted when status is 'Ready for Delivery'.")
		self.checks_parts_availability()

	def on_submit(self):
		self.deduct_part_stock()
		self.create_service_invoice()
		frappe.publish_realtime(
			"job_ready",
			{
				"job_card": self.name,
				"customer_name": self.customer_name,
				"status": self.status,
			},
			user=self.owner,
		)
		frappe.enqueue(
			"quickfix.quickfix.doctype.job_card.job_card.send_job_ready_email",
			job_card_name=self.name,
		)

	def on_cancel(self):
		self.status="Cancelled"
		for item in self.parts_used:
			stockqty = flt(frappe.db.get_value("Spare part", item.part_name, "stock_qty"))
			newqty = stockqty + flt(item.quantity)
			frappe.db.set_value(
				"Spare Part",
				item.part_name,
				"stock_qty",
				newqty,
				ignore_permissions=True,
			)
		doc_name = frappe.get_value("Service Invoice", {"job_card": self.name}, "name")
		if doc_name:
			frappe.get_doc("Service Invoice", doc_name).cancel()

	def on_trash(self):
		if self.status not in ["Draft", "Cancelled"]:
			frappe.throw(
				"Job Card can only be deleted when it is Draft or Cancelled."
			)

	def on_update(self):
		# on_update is triggered by save(). Calling self.save() here would re-enter
		# on_update and create a recursion loop. Instead, keep update-side effects
		# in helper methods that are called once per save operation.
		self.recalculate_amounts()

	def recalculate_amounts(self):
		self.calculate_parts_total()
		self.set_final_amount()

	def deduct_part_stock(self):
		if self.parts_used:
			for part in self.parts_used:
				stock_quantity = flt(frappe.db.get_value("Spare Part", part.part_name, "stock_qty"))
				new_quantity = stock_quantity - flt(part.quantity)
				# This deduction is part of an internal submit workflow, not a direct user edit of Spare Part.
				# ignore_permissions=True is acceptable because the Job Card submit process has already
				# validated the operation and this update reflects trusted system behavior.
				frappe.db.set_value(
					"Spare Part",
					part.part_name,
					"stock_qty",
					new_quantity,
					ignore_permissions=True,
				)

	def create_service_invoice(self):
		invoice = frappe.get_doc(
			{
				"doctype": "Service Invoice",
				"naming_series": "INV-.YYYY.-.#####",
				"job_card": self.name,
				"customer_name": self.customer_name,
				"labour_charge": self.labour_charge,
				"parts_total": self.parts_total,
				"total_amount": self.final_amountc,
				"payment_status": "Unpaid",
			}
		)
		invoice.insert(ignore_permissions=True)

	def checks_parts_availability(self):
		if self.parts_used:
			for part in self.parts_used:
				stk_qty = frappe.db.get_value("Spare Part", part.part_name, "stock_qty")
				if flt(stk_qty) < flt(part.quantity):
					frappe.throw(
						f"Not enough stock for part {part.part_name}. Available: {stk_qty}, Required: {part.quantity}"
					)

	def validate_customer_phone(self):
		if self.customer_phone:
			phone = self.customer_phone.strip()
			if not re.fullmatch(r"\d{10}", phone):
				frappe.throw("Customer phone number must be exactly 10 digits.")
			self.customer_phone = phone

	def validate_assigned_technician(self):
		if self.status in ["In Repair", "Ready for Delivery", "Delivered"] and not self.assigned_technician:
			frappe.throw(
				"Assigned technician is required when status is In Repair, Ready for Delivery, or Delivered."
			)

	def calculate_parts_total(self):
		parts_total = 0.0
		if self.parts_used:
			for row in self.parts_used:
				row.total_price = flt(row.quantity) * flt(row.unit_price)
				parts_total += flt(row.total_price)
		self.parts_total = parts_total

	def set_labour_charge(self):
		if not self.labour_charge:
			settings = frappe.db.get_single("Quickfix Settings")
			self.labour_charge = flt(settings.default_labour_charge)

	def set_final_amount(self):
		self.final_amountc = flt(self.parts_total) + flt(self.labour_charge)


def send_job_ready_email(job_card_name):
	job_card = frappe.get_doc("Job Card", job_card_name)
	if not job_card.customer_email:
		return

	frappe.sendmail(
		recipients=[job_card.customer_email],
		subject=f"Your repair job {job_card.name} is ready",
		message=(
			f"Hello {job_card.customer_name},\n\n"
			f"Your job card {job_card.name} is ready for pickup.\n"
			f"Total amount due: {job_card.final_amountc}.\n\n"
			"Thank you for choosing Quickfix."
		),
		reference_doctype="Job Card",
		reference_name=job_card.name,
	)


