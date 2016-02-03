# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import cint

def print_settings_for_item_table(doc):
	
	doc.print_templates = {
		"description": "templates/print_formats/includes/item_table_description.html",
		"qty": "templates/print_formats/includes/item_table_qty.html"
	}
	customised_print_preview = cint(frappe.db.get_value("Features Setup", None, "customised_print_preview"))
	
	doc.hide_in_print_layout = ["item_code", "item_name", "image", "uom", "stock_uom"]

	if customised_print_preview:
		
		visible_fieldname = get_visible_fieldname(doc.doctype)
		for field in visible_fieldname:
			if field not in doc.hide_in_print_layout:
				doc.hide_in_print_layout.append(field)

@frappe.whitelist()
def get_visible_fieldname(docname):
	
	fieldnames=[]

	for d in frappe.db.sql("""select fieldname from `tabDocField`
			where parent = %(parent)s
			and fieldtype not in ("Section Break", "Column Break", "Button")
			and print_hide = 0""", {
				"parent": docname
			}, as_dict = 1):
		
		if d.fieldname not in ("description", "qty", "rate", "amount", "stock_uom", "uom","item_code", "item_name"):
			fieldnames.append(d.fieldname)
	
	for d in frappe.db.sql("""select field_name, value from `tabProperty Setter` 
					where doc_type = %(doctype)s
					and property = 'print_hide'""", {
						"doctype": docname
					}, as_dict = 1):
		
		if cint(d.value) == 0:
			fieldnames.append(d.field_name)
		elif cint(d.value) == 1:
			if d.field_name in fieldnames:
				fieldnames.remove(d.field_name)
	
	return fieldnames
