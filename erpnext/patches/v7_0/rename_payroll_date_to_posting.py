from __future__ import unicode_literals
import frappe

from frappe.model.utils.rename_field import rename_field

def execute():
	dt = "Salary Slip"
	frappe.reload_doctype(dt)
	rename_field(dt, "payroll_date", "posting_date")