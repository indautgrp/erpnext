# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import nowdate
from erpnext.accounts.doctype.gl_entry.gl_entry import update_outstanding_amt

def execute():
	frappe.reload_doctype("Sales Invoice")
	return_entries = frappe.get_list("Sales Invoice",
        filters={"outstanding_amount": (">", "0.00"), "docstatus": 1, "due_date": ("<=", nowdate())},
		fields=["debit_to", "customer", "name"])
	for d in return_entries:
		print d.name
		update_outstanding_amt(d.debit_to, "Customer", d.customer, "Sales Invoice", d.name)

