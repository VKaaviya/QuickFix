# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Sparepart(Document):
	def before_save(self):
		if self.selling_price < self.unit_cost:
			frappe.throw("Selling price mjust be less than unit cost")
