frappe.provide("erpnext.project_statements");

erpnext.project_statements = {

	"formatter": function(row, cell, value, columnDef, dataContext, default_formatter) {

		if (columnDef.df.fieldname=="row_labels") {
			value = dataContext.showing_labels;
			columnDef.df.link_onclick =
				"erpnext.project_statements.open_time_log(" + JSON.stringify(dataContext) + ")";
			columnDef.df.is_tree = true;
		}
		
		value = default_formatter(row, cell, value, columnDef, dataContext);

		if (dataContext.indent==0 || dataContext.indent==1 || dataContext.showing_labels=="Grand Total") {
			var $value = $(value).css("font-weight", "bold");
			value = $value.wrap("<p></p>").parent().html();
		}

		return value;
	},
	"open_time_log": function(data) {
		if (!data.row_labels) return;
		if (data.indent == 1){
		    if (data.type == 'Project')
		        frappe.set_route("Form", "Project", data.row_labels);
		    else if (data.type == 'Issue')
		        frappe.set_route("Form", "Issue", data.row_labels);
		}
		if (data.indent == 5)
		    frappe.set_route("Form", "Time Log", data.showing_labels);
	}
}
