// Copyright (c) 2026, Kaviya and contributors
// For license information, please see license.txt

frappe.query_reports["Spare parts inventory"] = {
	// filters: [
	// 	// {
	// 	// 	"fieldname": "my_filter",
	// 	// 	"label": __("My Filter"),
	// 	// 	"fieldtype": "Data",
	// 	// 	"reqd": 1,
	// 	// },
	// ],
	formatter(value, row, column, data, default_formatter) {
			value = default_formatter(value, row, column, data);

        if (data&& data.quandity < data.reorder_level) {

            value = `<div style="
                background-color:#ffcccc;";>${value}</div>`;   
			     }

        return value;
	}
};
