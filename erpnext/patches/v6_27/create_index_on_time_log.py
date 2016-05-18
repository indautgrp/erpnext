import frappe

def execute():
	frappe.db.sql('''alter table `tabTime Log` add index idx_combine(date_worked,employee,activity_type,project,support_ticket)''')
