# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname


class Sparepart(Document):
	def before_save(self):
		if self.selling_price < self.unit_cost:
			frappe.throw("Selling price must be greater than unit cost")

	def autoname(self):
		if self.part_code:
			self.part_code = self.part_code.upper()
		self.name = make_autoname(self.meta.autoname, doc=self)

