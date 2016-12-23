// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["TAX Analytics"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1
        },
        {
            "fieldname": "date_range",
            "label": __("Date Range"),
            "fieldtype": "Data",
            "reqd": 1,
            on_change:function(){}//empty handle so refresh is triggered by daterange picker
        },
        {
            "fieldname": "accounting",
            "label": __("Accounting"),
            "fieldtype": "Select",
            "options": "Accrual Accounting\nCash Accounting",
            "default": "Accrual Accounting"
        }
    ],
    "formatter":  function(row, cell, value, columnDef, dataContext, default_formatter) {
        var me = this

        if (columnDef.df.fieldname == "rate") {
            value = dataContext.rate;
            
            columnDef.df.link_onclick = "frappe.query_reports[\"TAX Analytics\"].open_sale_purchase_journal(" + JSON.stringify(dataContext) + ")";
            
            columnDef.df.is_tree = true;
        }
                    
        value = default_formatter(row, cell, value, columnDef, dataContext);
            
        if (dataContext.indent == 0 || dataContext.rate == "Grand Total") {
            var $value = $(value).css("font-weight", "bold");
            value = $value.wrap("<p></p>").parent().html();
        }
        
        if (dataContext.sales_value == "0.00")
            dataContext.sales_value = "";
        if (dataContext.purchase_value == "0.00")
            dataContext.purchase_value = "";
        if (dataContext.tax_paid == "0.00")
            dataContext.tax_paid = "";
        if (dataContext.tax_collected == "0.00")
            dataContext.tax_collected = "";

        if (dataContext.tax_collected < 0.0 || dataContext.tax_paid < 0.0) {
            var $value = $(value).css("color", "red");
            value = $value.wrap("<p></p>").parent().html();
        }

        return value;
    },
    "open_sale_purchase_journal": function(data) {
        if (!data.rate) 
            return;
        
        if (data.indent == 1){
            var dr = data.rate;
            dr = dr.substr(0, dr.indexOf(':'));
            if (data.rate.indexOf("SINV") >= 0)
                frappe.set_route("Form", "Sales Invoice", dr);
            if (data.rate.indexOf("PINV") >= 0)
                frappe.set_route("Form", "Purchase Invoice", dr);
            if (data.rate.indexOf("JV") >= 0)
                frappe.set_route("Form", "Journal Entry", dr);
        }
    },
    "tree": true,
    "name_field": "rate",
    "parent_field": "parent_labels",
    "initial_depth": 1,
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
                    'Financial Year': [moment(frappe.defaults.get_default("year_start_date"), "YYYY-MM-DD"), moment(frappe.defaults.get_default("year_end_date"), "YYYY-MM-DD")],
                    'Last Financial Year': [moment(frappe.defaults.get_default("year_start_date"), "YYYY-MM-DD").subtract(1, 'year'), moment(frappe.defaults.get_default("year_end_date"), "YYYY-MM-DD").subtract(1, 'year')]
                },
                "locale": {
                    "format": "DD-MM-YYYY",
                    "firstDay": 1,
                    "cancelLabel": "Clear"
                }, 
                "startDate": moment().subtract(3, 'month').startOf('month'),
                "endDate": moment(),
                "linkedCalendars": false,
                "alwaysShowCalendars": true,
                "cancelClass": "date-range-picker-cancel "+"",
                "autoUpdateInput": true
            }).on('apply.daterangepicker',function(ev,picker){
                $(this).val(picker.startDate.format('DD-MM-YYYY') + ' - ' + picker.endDate.format('DD-MM-YYYY'));
                frappe.query_report.trigger_refresh();
            })
    }
};