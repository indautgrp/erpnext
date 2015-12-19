from __future__ import unicode_literals
import frappe

def execute():
	frappe.db.sql("""UPDATE `tabCustom Script` SET script = REPLACE(script, 'Support Ticket', 'Issue')""")
