import frappe

def execute():
	for doctype in ('Sales Order', 'Purchase Order', 'Sales Invoice',
		'Purchase Invoice'):
		frappe.reload_doctype(doctype)
		frappe.db.sql('''update `tab{0}` set submit_on_creation=0, notify_by_email=0
			where is_recurring=1'''.format(doctype))
