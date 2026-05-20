# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname


class Sparepart(Document):
	def before_save(self):
		if self.selling_price <= self.unit_cost:
			frappe.throw("Selling price must be greater than unit cost")

	def autoname(self):
		if self.part_code:
			self.part_code = self.part_code.upper()
		self.name = make_autoname(self.meta.autoname, doc=self)

	def on_update(self):
		threshold = frappe.db.get_value(
			"QuickFix Settings",
			None,
			"low_stock_threshold",
		)

		if threshold is None:
			return

		try:
			threshold = int(threshold)
		except (TypeError, ValueError):
			return

		if self.stock_qty is not None and self.stock_qty <= threshold:
			frappe.msgprint(
				f"Spare part {self.part_code or self.name} is at or below low stock threshold ({threshold}).",
			)


