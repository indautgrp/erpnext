var get_filters = function() {
	var filters = [
		{
			"fieldname":"from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.defaults.get_default("year_start_date")
		},
		{
			"fieldname":"to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.defaults.get_default("year_end_date")
		},
		{
			"fieldname":"company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1,
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldtype": "Break"
		}
	]
	frappe.call({
		method: "erpnext.hr.report.employee_leave_balance.employee_leave_balance.get_leave_type",
		async: false,
		callback: function (r) {
			var leave_types = r.message.split("\n");

			for (var x = 0; x <= leave_types.length - 1; x++) {
				leave_types[x];
				if (leave_types[x] == "Annual Leave" || leave_types[x] == "Sick Leave" || leave_types[x] == "Time in lieu") {
					df = {
						"fieldname": leave_types[x].toLowerCase().replace(/ /g, '_'),
						"label": __(leave_types[x]),
						"fieldtype": "Check",
						"default": 1
					};
				}
				else {
					df = {
						"fieldname": leave_types[x].toLowerCase().replace(/ /g, '_'),
						"label": __(leave_types[x]),
						"fieldtype": "Check"
					};
				}
				filters.push(df)
			}

		}
	});
	return filters
}

frappe.query_reports["Employee Leave Balance"] = {
	filters: get_filters()
}
