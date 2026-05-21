# Copyright (c) 2026, Kaviya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import random_string

from quickfix.quickfix.doctype.job_card.job_card import JobCard
from quickfix.quickfix.overrides.custom_job_card import CustomJobCard
from unittest.mock import patch


EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


# ─────────────────────────────────────────────────────────────────────────────
# Factory Functions
# ─────────────────────────────────────────────────────────────────────────────

def make_device_type():
	"""Create and return a fresh Device Type."""

	return frappe.get_doc({
		"doctype": "Device Type",
		"device_type": f"_Test Device Type {random_string(5)}"
	}).insert(ignore_permissions=True)


def make_technician():
	"""Create and return a fresh Technician."""

	return frappe.get_doc({
		"doctype": "Technician",
		"technician_name": f"_Test Technician {random_string(5)}",
		"phone": "9000000000",
		"specialization": "Laptop",
		"email": f"test_{random_string(5)}@example.com",
		"status": "Active",
	}).insert(ignore_permissions=True)


def make_spare_part(unit_cost=100.0,selling_price=200.0,stock_qty=10):
	"""Create and return a fresh Spare Part."""

	return frappe.get_doc({
		"doctype": "Spare part",
		"part_name": f"_Test Spare Part {random_string(5)}",
		"unit_cost": unit_cost,
		"selling_price": selling_price,
		"stock_qty": stock_qty
	}).insert(ignore_permissions=True)


def make_job_card(**overrides):
	"""Create and return a Job Card."""

	device_type = overrides.pop(
		"device_type",
		None
	) or make_device_type()

	technician = overrides.pop(
		"technician",
		None
	) or make_technician()

	defaults = {
		"doctype": "Job Card",
		"customer_name": "_Test Customer",
		"customer_phone": "9000000001",
		"customer_email": "testcustomer@example.com",
		"device_type": device_type.name,
		"assigned_technician": technician.name,
		"problem_description": "Screen not working",
		"status": "Draft",
		"priority": "Normal",
		"parts_used": [],
		"estimate_cost":10.0
	}

	defaults.update(overrides)

	return frappe.get_doc(defaults).insert(
		ignore_permissions=True
	)


# ─────────────────────────────────────────────────────────────────────────────
# Test Class
# ─────────────────────────────────────────────────────────────────────────────

class IntegrationTestJobCard(IntegrationTestCase):

	def setUp(self):

		frappe.set_user("Administrator")

		self.device_type = make_device_type()

		self.technician = make_technician()

		self.spare_part = make_spare_part(stock_qty=20)

		self.job_card = make_job_card(
			device_type=self.device_type,
			technician=self.technician,
		)

	# ─────────────────────────────────────────────────────────────────────
	# Tests
	# ─────────────────────────────────────────────────────────────────────

	def test_job_card_creation(self):
		"""Test Job Card draft creation."""

		self.assertEqual(self.job_card.docstatus, 0)

	def test_phone_number_validation(self):
		"""Test customer phone validation."""

		job = make_job_card()

		job.customer_phone = "12345"

		with self.assertRaises(frappe.ValidationError):
			job.validate()

		job.customer_phone = "123456789000"

		with self.assertRaises(frappe.ValidationError):
			job.validate()

		job.customer_phone = "1234567abcd"

		with self.assertRaises(frappe.ValidationError):
			job.validate()

		job.customer_phone = "9876543210"

		job.validate()

		self.assertEqual(job.customer_phone,"9876543210")

	def test_custom_job_card_validate_must_call_parent_validate(self):
		"""Ensure override validate() calls parent validate()."""
		with patch.object(JobCard, "validate", autospec=True) as mock_validate:


			doc = CustomJobCard({
				"doctype": "Job Card"
			})

			doc.priority = "Urgent"

			doc.assigned_technician = None

			doc.validate()

			mock_validate.assert_called_with(doc)

	def test_final_amount(self):
		"""Test final amount calculation."""

		spare_part_1 = make_spare_part(unit_cost=100.0,selling_price=150.0,stock_qty=20)

		spare_part_2 = make_spare_part(unit_cost=200.0,selling_price=300.0,stock_qty=20)

		job_card = make_job_card()

		job_card.append("parts_used", {
			"part": spare_part_1.name,
			"quandity": 2,
			"unit_price": spare_part_1.selling_price
		})

		job_card.append("parts_used", {
			"part": spare_part_2.name,
			"quandity": 1,
			"unit_price": spare_part_2.selling_price
		})

		job_card.save()

		part_total = ((150.0 * 2) +(300.0 * 1))

		final_amount = (part_total +job_card.labour_charge)

		self.assertEqual(job_card.parts_total,part_total)

		self.assertEqual(job_card.final_amountc,final_amount)

	def test_technician_assigned(self):
		"""Test technician assignment validation."""

		job_card = make_job_card(status="In Repair")

		job_card.assigned_technician = None

		with self.assertRaises(frappe.ValidationError):
			job_card.validate()

		technician = make_technician()

		job_card.assigned_technician = technician.name

		job_card.save()

		self.assertEqual(job_card.assigned_technician,technician.name)
	def test_estimate_cost_validation(self):
		"""Test estimated cost validation when status is In Repair."""

		job_card=make_job_card(status="In Repair")
		job_card.estimate_cost = 0.0

		with self.assertRaises(frappe.ValidationError):
			job_card.save()
			job_card.submit()
		
	def test_child_table_computation(self):
		"""Test total price computation in parts_used child table."""

		spare_part_1 = make_spare_part(unit_cost=50.0,selling_price=100.0,stock_qty=20)
		spare_part_2 = make_spare_part(unit_cost=30.0,selling_price=60.0,stock_qty=20)

		job_card = make_job_card()

		job_card.append("parts_used", {
			"part": spare_part_1.name,
			"quandity": 3
		})
		job_card.append("parts_used", {
			"part": spare_part_2.name,
			"quandity": 5
		})

		job_card.save()

		part_row_1 = job_card.parts_used[0]
		part_row_2 = job_card.parts_used[1]


		self.assertEqual(part_row_1.total_price, 300.0)
		self.assertEqual(part_row_2.total_price, 300.0)
		self.assertEqual(job_card.parts_total,600.0)

	def test_submit_validation(self):
		"""Test validations on submit."""

		job_card = make_job_card(status="In Repair")

		with self.assertRaises(frappe.ValidationError):
			job_card.submit()
		job_card.reload()
		job_card.status="Ready for Delivery"

		job_card.save()

		job_card.submit()

		self.assertEqual(job_card.docstatus, 1)
	def test_parts_availability_check(self):
		"""Test parts availability check."""

		spare_part = make_spare_part(stock_qty=0)

		job_card = make_job_card(status="Ready for Delivery")

		job_card.append("parts_used", {
			"part": spare_part.name,
			"quandity": 1
		})
		job_card.save()
		with self.assertRaises(frappe.ValidationError):
			job_card.submit()
		job_card.reload()
		spare_part.stock_qty=5
		spare_part.save()
		job_card.submit()
		self.assertEqual(job_card.parts_used[0].part,spare_part.name)
	def test_deduct_stock(self):
		"""Test stock deduction on submit."""

		spare_part_1 = make_spare_part(unit_cost=50.0,selling_price=100.0,stock_qty=20)
		spare_part_2 = make_spare_part(unit_cost=30.0,selling_price=60.0,stock_qty=20)

		job_card = make_job_card(status="Ready for Delivery")

		job_card.append("parts_used", {"part": spare_part_1.name,"quandity": 3})
		job_card.append("parts_used", {"part": spare_part_2.name,"quandity": 5})

		job_card.save()
		job_card.submit()

		self.assertEqual(frappe.db.get_value("Spare part",spare_part_1.name,"stock_qty"),17)
		self.assertEqual(frappe.db.get_value("Spare part",spare_part_2.name,"stock_qty"),15)

		job_card.cancel()
		self.assertEqual(frappe.db.get_value("Spare part",spare_part_1.name,"stock_qty"),20)
		self.assertEqual(frappe.db.get_value("Spare part",spare_part_2.name,"stock_qty"),20)

	def test_service_invoice_creation(self):
		"""Test Service Invoice creation on submit."""

		job_card = make_job_card(status="Ready for Delivery")

		job_card.append("parts_used", {
			"part": self.spare_part.name,
			"quandity": 2
		})

		job_card.save()
		job_card.submit()

		invoice = frappe.get_doc("Service Invoice", {"job_card": job_card.name})

		self.assertIsNotNone(invoice)
		self.assertEqual(invoice.job_card, job_card.name)
		self.assertEqual(invoice.total_amount, job_card.final_amountc)
		self.assertEqual(invoice.payment_status, "Unpaid")

		job_card.payment_status = "Paid"
		job_card.save()
		invoice.reload()
		self.assertEqual(invoice.payment_status, "Paid")

	def test_invoice_cancellation(self):
		"""Test Service Invoice cancellation on Job Card cancellation."""

		job_card = make_job_card(status="Ready for Delivery")
		job_card.submit()

		invoice_name = frappe.db.get_value("Service Invoice", {"job_card": job_card.name}, "name")
		self.assertIsNotNone(invoice_name)

		job_card.cancel()

		invoice_docstatus = frappe.db.get_value("Service Invoice", invoice_name, "docstatus")
		self.assertEqual(invoice_docstatus, 2)
		self.assertEqual(job_card.status, "Cancelled")

	def test_trash_validation(self):
		"""Test validation on delete."""

		job_card = make_job_card(status="Ready for Delivery")

		job_card.submit()

		#delete connected invoice and then delete job card
		invoice=frappe.get_doc("Service Invoice", {"job_card": job_card.name})
		invoice.cancel()
		invoice.delete()

		with self.assertRaises(frappe.ValidationError):
			job_card.delete()
		
		
		
		job_card.cancel()

		job_card.delete()

		self.assertFalse(frappe.db.exists("Job Card", job_card.name))
	# def test_mock_mail(self):
	# 	"""Test that validate method is called when we mock it."""
	# 	with patch("frappe.sendmail") as mock_sendmail:

	# 		job_card=make_job_card(status="Ready for Delivery")

	# 		job_card.save()
	# 		job_card.submit()
	# 		mock_sendmail.assert_any_call()
	# 		args,kwargs=mock_sendmail.call_args
	# 		self.assertEqual(kwargs["recipients"], [job_card.customer_email])

	def test_enqueue(self):
		"""Test that validate method is called when we mock it."""
		with patch("frappe.enqueue") as mock_enqueue:

			job_card = make_job_card(status="Ready for Delivery")
			job_card.save()
			job_card.submit()

			mock_enqueue.assert_any_call("quickfix.quickfix.doctype.job_card.job_card.send_job_ready_email",job_card_name=job_card.name)
	
	def test_realtime_publish(self):
		"""Test that validate method is called when we mock it."""
		with patch("frappe.publish_realtime") as mock_publish_realtime:

			job_card = make_job_card(status="Ready for Delivery")
			job_card.save()
			job_card.submit()

			mock_publish_realtime.assert_any_call(
					"job_ready",
				{
					"job_card":job_card.name,
					"customer_name": job_card.customer_name,
					"status": job_card.status,
				},
				user=job_card.owner,
			)
	def test_webhook_enqueue_on_submit(self):
		"""Test that webhook is enqueued on submit."""
		with patch("frappe.enqueue") as mock_enqueue:

			job_card = make_job_card(status="Ready for Delivery")
			job_card.save()
			job_card.submit()

			mock_enqueue.assert_any_call(
				"quickfix.webhooks.send_webhook",
				queue="short",
				job_card_name=job_card.name,
				webhook_id=mock_enqueue.call_args.kwargs["webhook_id"]
			)
	def test_duplicate_invoice(self):
		"""Test that duplicate service invoice is not created on multiple submits."""
		job_card=make_job_card(status="Ready for Delivery")
		job_card.save()
		job_card.submit()
		import quickfix.quickfix.doctype.job_card.job_card as job_card_module
		job_card_module.JobCard.on_submit(job_card)

		invoices=frappe.get_all("Service Invoice", filters={"job_card": job_card.name})
		self.assertEqual(len(invoices),1)
	
	def test_same_part_used_twice(self):
		"""Test same spare part added twice in child table."""

		spare_part = make_spare_part(
			unit_cost=100.0,
			selling_price=150.0,
			stock_qty=20
		)

		job_card = make_job_card()

		job_card.append("parts_used", {
			"part": spare_part.name,
			"quandity": 2,
			"unit_price": 150.0
		})

		job_card.append("parts_used", {
			"part": spare_part.name,
			"quandity": 3,
			"unit_price": 150.0
		})

		job_card.save()

		self.assertEqual(
			job_card.parts_used[0].total_price,
			300.0
		)

		self.assertEqual(
			job_card.parts_used[1].total_price,
			450.0
		)

		self.assertEqual(job_card.parts_total, 750.0)


	def test_zero_quantity_row(self):
		"""Test zero quantity row validation."""

		spare_part = make_spare_part(stock_qty=10)

		job_card = make_job_card()

		job_card.append("parts_used", {
			"part": spare_part.name,
			"quandity": 0,
			"unit_price": 100.0
		})

		with self.assertRaises(frappe.ValidationError):
			job_card.save()


	def test_double_cancellation(self):
		"""Test cancelling already cancelled Job Card."""

		job_card = make_job_card(
			status="Ready for Delivery"
		)

		job_card.save()

		job_card.submit()

		job_card.cancel()

		with self.assertRaises(frappe.ValidationError):
			job_card.cancel()



