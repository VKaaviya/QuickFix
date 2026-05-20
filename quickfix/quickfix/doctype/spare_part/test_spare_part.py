# Copyright (c) 2026, Kaviya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from quickfix.quickfix.doctype.job_card.test_job_card import make_spare_part

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestSparepart(IntegrationTestCase):
	"""
	Integration tests for Sparepart.
	Use this class for testing interactions between multiple components.
	"""

	def test_unit_cost_selling_cost_validation(self):
		"""Test that selling price must be greater than unit cost."""
		spare_part=make_spare_part()
		
		spare_part.unit_cost = 100.0
		spare_part.selling_price = 90.0
		with self.assertRaises(frappe.ValidationError):
			spare_part.save()
		spare_part.reload()

		spare_part.unit_cost=100.0
		spare_part.selling_price=100.0
		with self.assertRaises(frappe.ValidationError):
			spare_part.save()
		spare_part.reload()

		spare_part.unit_cost=100.0
		spare_part.selling_price=101.0
		spare_part.save()
		self.assertEqual(spare_part.unit_cost, 100.0)
		self.assertEqual(spare_part.selling_price, 101.0)




