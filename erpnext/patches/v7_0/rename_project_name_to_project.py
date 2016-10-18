from __future__ import unicode_literals
import frappe

from frappe.model.utils.rename_field import rename_field

def execute():
    for dt in ("gl_entry","Journal Entry Account","Sales Invoice","Journal Entry","Purchase Invoice","Purchase Receipt","general_ledger","accounts_controller","stock_controller"):
        frappe.reload_doctype(dt)
        rename_field(dt, "project_name", "project")