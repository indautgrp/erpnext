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

frappe.ui.form.on("Time Log Approve Detail", "rejected", function(frm, cdt, cdn) {
	var item = frappe.get_doc(cdt,cdn);
	if (item.rejected) {
		if (item.approved) {
			frappe.model.set_value(cdt, cdn, "rejected", 0);

			frappe.confirm(__("Do you want to reset Approved check box?"), function() {
							
						frappe.model.set_value(cdt, cdn, "approved", 0);
						frappe.model.set_value(cdt, cdn, "rejected", 1);						
			});
			
		}
	}

});

frappe.ui.form.on("Time Log Approve Detail", "approved", function(frm, cdt, cdn) {
	var item = frappe.get_doc(cdt,cdn);
	if (item.approved) {
		if (item.rejected) {
			frappe.model.set_value(cdt, cdn, "approved", 0);

			frappe.confirm(__("Do you want to reset Rejected check box?"), function() {
							
						frappe.model.set_value(cdt, cdn, "rejected", 0);
						frappe.model.set_value(cdt, cdn, "approved", 1);
				
			});
			
		}
	}

});