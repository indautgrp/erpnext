from __future__ import unicode_literals
import frappe

from frappe.model.utils.rename_field import rename_field

def execute():
    for dt in ("GL Entry", "Journal Entry", "Journal Entry Account", "Purchase Invoice Item", "Sales Invoice", "Delivery Note", "Purchase Receipt Item", "Stock Entry"):
        frappe.reload_doctype(dt)
        rename_field(dt, "project_name", "project")