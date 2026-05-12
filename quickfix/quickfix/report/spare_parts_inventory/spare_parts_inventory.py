# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
	"""Return columns and data for the report.

	This is the main entry point for the report. It accepts the filters as a
	dictionary and should return columns and data. It is called by the framework
	every time the report is refreshed or a filter is updated.
	"""
	columns = get_columns()
	data = get_data()
	report_summary = get_report_summary(data)
	return columns, data,None,None,report_summary


def get_columns() -> list[dict]:
	"""Return columns for the report.

	One field definition per column, just like a DocType field definition.
	"""
	cols=[
		{
			"label": _("Part Name"),
			"fieldname": "part_name",
			"fieldtype": "Data",
		},
		{
			"label":_("Part Code"),
			"fieldname": "part_code",
   			"fieldtype": "Data",
		},
		{
			"label":_("Device Type"),
			"fieldname": "device_type",
			"fieldtype": "Link",
			"options": "Device Type",
		},
		{
			"label":_("Stock Qty"),	
			"fieldname": "quandity",
			"fieldtype": "Int",
		},
		{
			"label":_("Reorder Level"),
			"fieldname": "reorder_level",
			"fieldtype": "Int",
		},
		{
			"label":_("Unit Cost"),
			"fieldname": "unit_cost",
			"fieldtype": "Currency",
			"precision": 2,
		},
		{
			"label":_("Total Value"),
			"fieldname": "total_value",
			"fieldtype": "Currency",
			"precision": 2,
		},
		{
			"label":_("Selling Price"),
			"fieldname": "selling_price",
			"fieldtype": "Currency",
			"precision": 2,
		},
		{
			"label":_("Margin %"),
			"fieldname": "margin_percent",
			"fieldtype": "Float",
		}

	]
	return cols

def get_data() -> list[list]:
	"""Return data for the report.

	The report data is a list of rows, with each row being a list of cell values.
	"""
	data=[]
	total_stock_qty = 0
	total_value = 0
	
	parts = frappe.get_list("Spare part", fields=["part_name", "part_code", "compatible_device_type", "stock_qty", "reorder_level", "unit_cost", "selling_price"])
	for part in parts:
		margin_percent = 0
		part_total_value = 0
		
		if part.unit_cost:
			margin_percent = ((part.selling_price - part.unit_cost) / part.unit_cost) * 100
			part_total_value = (part.stock_qty or 0) * part.unit_cost
		
		total_stock_qty += (part.stock_qty or 0)
		total_value += part_total_value
		
		data.append({
			"part_name": part.part_name,
			"part_code": part.part_code or "Nill",
			"device_type": part.compatible_device_type,
			"quandity": part.stock_qty,
			"reorder_level": part.reorder_level or 0,
			"unit_cost": part.unit_cost,
			"total_value": part_total_value,
			"selling_price": part.selling_price,
			"margin_percent": margin_percent,
		})
	
	# Add total row
	data.append({
		"part_name": "TOTAL",
		"part_code": "",
		"device_type": "",
		"quandity": total_stock_qty,
		"reorder_level": "",
		"unit_cost": "",
		"total_value": total_value,
		"selling_price": "",
		"margin_percent": "",
	})
	
	return data

def get_report_summary(data):
	total_parts=len(data)-1
	below_reorder =sum(1 for d in data if d["reorder_level"]!="" and d["quandity"] < d["reorder_level"])
	total_inventory_value=sum(d["quandity"] * d["unit_cost"] for d in data if d["unit_cost"]!="")
	return[
		{
			"label":_("Total Parts"),
			"value": total_parts,
			"indicator":"lightblue",
		},
		{
			"label":_("Parts Below Reorder Level"),
			"value": below_reorder,
			"indicator":"red",
		},
		{
			"label":_("Total Inventory Value"),
			"value": total_inventory_value,
			"indicator":"green",
		}
	]