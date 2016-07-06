import frappe
from erpnext.controllers.recurring_document import manage_recurring_documents

def execute():

	frappe.db.sql("""update `tabSales Invoice` 
				set is_recurring=1 where (docstatus=1 or docstatus=0)
				and (next_date='2016-06-25' or next_date='2016-06-26') and is_recurring=0 and name!='SINV-12230'""")
	
	manage_recurring_documents("Sales Invoice", "2016-06-25")
	manage_recurring_documents("Sales Invoice", "2016-06-26")
