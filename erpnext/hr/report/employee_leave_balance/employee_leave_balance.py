# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt
from erpnext.hr.doctype.leave_application.leave_application \
	import get_leave_allocation_records, get_leave_balance_on, get_approved_leaves_for_period


def execute(filters=None):
	leave_types = frappe.db.sql_list("select name from `tabLeave Type` order by name asc")
	
	columns = get_columns(filters, leave_types)
	data = get_data(filters, leave_types)
	
	return columns, data
	
def get_columns(filters, leave_types):
	columns = [
		_("Employee") + ":Link/Employee:150", 
		_("Employee Name") + "::200", 
		_("Department") +"::150"
	]

	for leave_type in leave_types:
		matched_leave_type = leave_type.lower().replace(' ','_')
		if filters.get(matched_leave_type):
			columns.append(_("New") + " " + _(leave_type) + " " + ":Float:160")
			columns.append(_("Total") + " " + _(leave_type) + " " + ":Float:160")
			columns.append(_(leave_type) + " " + _("Taken") + ":Float:160")
			columns.append(_(leave_type) + " " + _("Balance") + ":Float:160")
		
	return columns
	
def get_data(filters, leave_types):

	allocation_records_based_on_to_date = get_leave_allocation_records(filters.to_date)

	active_employees = frappe.get_all("Employee", 
		filters = { "status": "Active", "company": filters.company}, 
		fields = ["name", "employee_name", "department"],
		order_by = "employee_name asc")
	
	data = []
	for employee in active_employees:
		row = [employee.name, employee.employee_name, employee.department]

		for leave_type in leave_types:	
			matched_leave_type = leave_type.lower().replace(' ','_')
			if filters.get(matched_leave_type):

				# leaves taken
				leaves_taken = get_approved_leaves_for_period(employee.name, leave_type, 
					filters.from_date, filters.to_date)
	
				# closing balance
				closing = get_leave_balance_on(employee.name, leave_type, filters.to_date, 
					allocation_records_based_on_to_date.get(employee.name, frappe._dict()))
			
				# annual leave allocated
				allocation_records = allocation_records_based_on_to_date.get(employee.name, frappe._dict())
				allocation = allocation_records.get(leave_type, frappe._dict())
				total_leaves_allocated = flt(allocation.total_leaves_allocated)
				new_leaves_allocated = flt(allocation.new_leaves_allocated)
				
				row += [new_leaves_allocated, total_leaves_allocated, leaves_taken, closing]
			
		data.append(row)
		
	return data

@frappe.whitelist()
def get_leave_type():
	leave_types = frappe.db.sql_list("select name from `tabLeave Type` order by name asc")
	return "\n".join(str(leave_type) for leave_type in leave_types)