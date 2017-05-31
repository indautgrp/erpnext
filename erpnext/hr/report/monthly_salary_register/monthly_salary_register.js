// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Monthly Salary Register"] = {
	"filters": [
		{
			"fieldname": "date_range",
			"label": __("Date Range"),
			"fieldtype": "Data",
			"reqd": 1,
			on_change:function(){}//empty handle so refresh is triggered by daterange picker
		},
		{
			"fieldname":"employee",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee"
		},
		{
			"fieldname":"company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname": "by",
			"label": __("By"),
			"fieldtype": "Select",
			"options": "Salary Slip\nPosting Date",
			"default": "Salary Slip"
		}
	],
	onload:function(){
		$("div[data-fieldname=date_range]").removeClass("col-md-2").addClass("col-lg-2 col-md-3").css("max-width","200px")
		$("input[data-fieldname=date_range]").daterangepicker({
			"autoApply": true,
			"showDropdowns": true,
			"ranges": {
				'Today': [moment(), moment()],
				'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
				'Last Week': [moment().subtract(1, 'week').startOf('week'), moment().subtract(1, 'week').endOf('week')],
				'Last 7 Days': [moment().subtract(6, 'days'), moment()],
				'Last 30 Days': [moment().subtract(29, 'days'), moment()],
				'This Month': [moment().startOf('month'), moment().endOf('month')],
				'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')],
				'Last 3 Months': [moment().subtract(3, 'month').startOf('month'), moment().endOf('month')],
				'This Quarter': [moment().startOf('quarter'), moment().endOf('quarter')],
				'Last Quarter': [moment().startOf('quarter').subtract(3, 'month'), 
					moment().endOf('quarter').subtract(3, 'month')],
				'Financial Year': [moment(frappe.defaults.get_default("year_start_date"), "YYYY-MM-DD"),
					moment(frappe.defaults.get_default("year_end_date"), "YYYY-MM-DD")],
				'Last Financial Year': [moment(frappe.defaults.get_default("year_start_date"), "YYYY-MM-DD").subtract(1, 'year'),
					moment(frappe.defaults.get_default("year_end_date"), "YYYY-MM-DD").subtract(1, 'year')]
			},
			"locale": {
				"format": "DD-MM-YYYY",
				"firstDay": 1,
				"cancelLabel": "Clear"
			}, 
			"startDate": moment().startOf('month'),
			"endDate": moment().endOf('month'),
			"linkedCalendars": false,
			"alwaysShowCalendars": true,
			"cancelClass": "date-range-picker-cancel "+"",
			"autoUpdateInput": true
		}).on('apply.daterangepicker',function(ev,picker){
			$(this).val(picker.startDate.format('DD-MM-YYYY') + ' - ' + picker.endDate.format('DD-MM-YYYY'));
			frappe.query_report.trigger_refresh();
		})
	}
}