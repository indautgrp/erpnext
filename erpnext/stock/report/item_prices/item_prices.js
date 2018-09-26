// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Item Prices"] = {
	"filters": [
		{
			"fieldname": "items",
			"label": __("Items Filter"),
			"fieldtype": "Select",
			"options": "Enabled Items only\nDisabled Items only\nAll Items",
			"default": "Enabled Items only",
			"on_change": function(query_report) {
				query_report.trigger_refresh();
			}
		}
	]
}