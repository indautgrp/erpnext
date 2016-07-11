// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

cur_frm.add_fetch('employee', 'company', 'company');
cur_frm.add_fetch('company', 'default_letter_head', 'letter_head');

// On load
// -------------------------------------------------------------------
cur_frm.cscript.onload = function(doc,dt,dn){
	if((cint(doc.__islocal) == 1) && !doc.amended_from){
		if(!doc.month) {
			var today=new Date();
			month = (today.getMonth()+01).toString();
			if(month.length>1) doc.month = month;
			else doc.month = '0'+month;
		}
		if(!doc.fiscal_year) doc.fiscal_year = sys_defaults['fiscal_year'];
		refresh_many(['month', 'fiscal_year']);
	}
}

// Get leave details
//---------------------------------------------------------------------
cur_frm.cscript.fiscal_year = function(doc,dt,dn){
		return $c_obj(doc, 'get_emp_and_leave_details','',function(r, rt) {
			var doc = locals[dt][dn];
			cur_frm.refresh();
			calculate_all(doc, dt, dn);
		});
}

cur_frm.cscript.month = cur_frm.cscript.employee = cur_frm.cscript.fiscal_year;

cur_frm.cscript.leave_without_pay = function(doc,dt,dn){
	if (doc.employee && doc.fiscal_year && doc.month) {
		return $c_obj(doc, 'get_leave_details', {"lwp": doc.leave_without_pay}, function(r, rt) {
			var doc = locals[dt][dn];
			cur_frm.refresh();
			calculate_all(doc, dt, dn);
		});
	}
}

var calculate_all = function(doc, dt, dn) {
	calculate_earning_total(doc, dt, dn);
	calculate_ded_total(doc, dt, dn);
	calculate_net_pay(doc, dt, dn);
}

cur_frm.cscript.e_modified_amount = function(doc,dt,dn){
	calculate_earning_total(doc, dt, dn);
	calculate_net_pay(doc, dt, dn);
}

cur_frm.cscript.e_depends_on_lwp = function(doc,dt,dn){
	calculate_earning_total(doc, dt, dn, true);
	calculate_net_pay(doc, dt, dn);
}
// Trigger on earning modified amount and depends on lwp
// ------------------------------------------------------------------------
cur_frm.cscript.d_modified_amount = function(doc,dt,dn){
	calculate_ded_total(doc, dt, dn);
	calculate_net_pay(doc, dt, dn);
}

cur_frm.cscript.d_depends_on_lwp = function(doc, dt, dn) {
	calculate_ded_total(doc, dt, dn, true);
	calculate_net_pay(doc, dt, dn);
};

// Calculate earning total
// ------------------------------------------------------------------------
var calculate_earning_total = function(doc, dt, dn, reset_amount) {
	var tbl = doc.earnings || [];

	var total_earn = 0;
	for(var i = 0; i < tbl.length; i++){
		if(cint(tbl[i].e_depends_on_lwp) == 1) {
			tbl[i].e_modified_amount =  Math.round(tbl[i].e_amount)*(flt(doc.payment_days) / 
				cint(doc.total_days_in_month)*100)/100;			
			refresh_field('e_modified_amount', tbl[i].name, 'earnings');
		} else if(reset_amount) {
			tbl[i].e_modified_amount = tbl[i].e_amount;
			refresh_field('e_modified_amount', tbl[i].name, 'earnings');
		}
		total_earn += flt(tbl[i].e_modified_amount);
	}
	doc.gross_pay = total_earn + flt(doc.arrear_amount) + flt(doc.leave_encashment_amount);
	refresh_many(['e_modified_amount', 'gross_pay']);
}

// Calculate deduction total
// ------------------------------------------------------------------------
var calculate_ded_total = function(doc, dt, dn, reset_amount) {
	var tbl = doc.deductions || [];

	var total_ded = 0;
	for(var i = 0; i < tbl.length; i++){
		if(cint(tbl[i].d_depends_on_lwp) == 1) {
			tbl[i].d_modified_amount = Math.round(tbl[i].d_amount)*(flt(doc.payment_days)/cint(doc.total_days_in_month)*100)/100;
			refresh_field('d_modified_amount', tbl[i].name, 'deductions');
		} else if(reset_amount) {
			tbl[i].d_modified_amount = tbl[i].d_amount;
			refresh_field('d_modified_amount', tbl[i].name, 'earnings');
		}
		total_ded += flt(tbl[i].d_modified_amount);
	}
	doc.total_deduction = total_ded;
	refresh_field('total_deduction');	
}

// Calculate net payable amount
// ------------------------------------------------------------------------
var calculate_net_pay = function(doc, dt, dn) {
	doc.net_pay = flt(doc.gross_pay) - flt(doc.total_deduction);
	doc.rounded_total = Math.round(doc.net_pay);
	refresh_many(['net_pay', 'rounded_total']);
}

// trigger on arrear
// ------------------------------------------------------------------------
cur_frm.cscript.arrear_amount = function(doc,dt,dn){
	calculate_earning_total(doc, dt, dn);
	calculate_net_pay(doc, dt, dn);
}

// trigger on encashed amount
// ------------------------------------------------------------------------
cur_frm.cscript.leave_encashment_amount = cur_frm.cscript.arrear_amount;

// validate
// ------------------------------------------------------------------------
cur_frm.cscript.validate = function(doc, dt, dn) {
	calculate_all(doc, dt, dn);
}

cur_frm.fields_dict.employee.get_query = function(doc,cdt,cdn) {
	return{
		query: "erpnext.controllers.queries.employee_query"
	}		
}

cur_frm.cscript.addremove_recipients = function(doc, dt, dn) {
	// Get user list
	return $c_obj(doc, 'get_users', '', function(r, rt) {
		if(r.exc) {
			msgprint(r.exc);
		} else {
			// Open a dialog and display checkboxes against email addresses
			doc = locals[dt][dn];
			var d = new frappe.ui.Dialog({
				title: __('Add/Remove Recipients'),
				width: 400
			});

			$.each(r.user_list, function(i, v) {

                var company_email = 'Company e-mail: ';
				company_email = company_email + " &lt;" + v.company_email + "&gt;";

                var personal_email = 'Personal e-mail: ';
				personal_email = personal_email + " &lt;" + v.personal_email + "&gt;";

				var user_id = 'User: ';
				user_id = user_id + " &lt;" + v.user_id + "&gt;";

				$('<div class="checkbox"><label>\
					<input type="checkbox" data-id="' + v.company_email + '"'+
						(v.checked_company ? 'checked' : '') +
				'> '+ company_email +'</label></div>').appendTo(d.body);

				$('<div class="checkbox"><label>\
					<input type="checkbox" data-id="' + v.personal_email + '"'+
						(v.checked_personal ? 'checked' : '') +
				'> '+ personal_email +'</label></div>').appendTo(d.body);

				$('<div class="checkbox"><label>\
					<input type="checkbox" data-id="' + v.user_id + '"'+
						(v.checked_user ? 'checked' : '') +
				'> '+ user_id +'</label></div>').appendTo(d.body);
			});

			// Display add recipients button
			d.set_primary_action("Update", function() {
				cur_frm.cscript.add_to_rec_list(doc, d.body, r.user_list.length);
			});

			cur_frm.rec_dialog = d;
			d.show();
		}
	});
}

cur_frm.cscript.add_to_rec_list = function(doc, dialog, length) {
	// add checked email to list of recipients
	var rec_list = [];
	$(dialog).find('input:checked').each(function(i, input) {
		rec_list.push($(input).attr('data-id'));
	});

	doc.recipients_list = rec_list.join('\n');
	cur_frm.rec_dialog.hide();
	cur_frm.save();
	cur_frm.refresh_fields();
}
