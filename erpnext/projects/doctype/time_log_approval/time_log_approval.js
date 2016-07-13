// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Time Log Approval', {

	onload: function(frm) {

		frm.set_value("from_date", frappe.datetime.month_start());
		frm.set_value("to_date", frappe.datetime.month_end());
	},

	refresh: function(frm) {
		frm.disable_save();
	},
	
	update_state: function(frm) {
		return frappe.call({
			method: "approve_time_log",
			doc: frm.doc,
			callback: function(r, rt) {
				frm.refresh()
			}
		});
	},

	get_relevant_entries: function(frm) {
		return frappe.call({
			method: "get_details",
			doc: frm.doc,
			callback: function(r, rt) {
				frm.refresh()
			}
		});
	}
});
