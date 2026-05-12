// Copyright (c) 2026, Kaviya and contributors
// For license information, please see license.txt

frappe.query_reports["Technician Perfomence Report"] = {
	filters: [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default":frappe.datetime.month_start(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default":frappe.datetime.month_end(),
			"reqd": 1
		},
		{
			"fieldname": "technician",
			"label": __("Technician"),
			"fieldtype": "Link",
			"options": "Technician"
		}
	],
	formatter(value, row, column, data, default_formatter) { 
		value = default_formatter(value, row, column, data); 
		if (column.fieldname === "completion_rate") 
			{ if (data.completion_rate < 70) { 
				value = `<span style="color:red;font-weight:bold">${value}</span>`; 
			} else if (data.completion_rate >= 90) { 
				value = `<span style="color:green;font-weight:bold">${value}</span>`; 
			} 
		} return value;
	 }
};
