from __future__ import unicode_literals
import frappe

def execute():
	frappe.reload_doctype('Employee')
	frappe.db.sql("update `tabEmployee` set prefered_contact_email = '' ")