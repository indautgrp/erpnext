import frappe

# patch all for-print field (total amount) in Journal Entry in 2015
def execute():
	updated_list = []

	for issue in frappe.db.sql_list("""select name from `tabIssue` where (contact is null or contact='') or (customer is null or customer='')"""):
		
		issue = frappe.get_doc("Issue", issue)
		
		if issue.raised_by: 
			contact = frappe.db.get_value("Contact", {"email_id": issue.raised_by}, "name")
			customer = frappe.db.get_value("Contact", {"email_id": issue.raised_by}, "customer")
			
			if contact and (not issue.contact or issue.contact ==''):
				updated_list.append(issue.name)
				issue.db_set("contact", contact, update_modified=False)
			
			if customer and (not issue.customer or issue.customer ==''):
				updated_list.append(issue.name)
				issue.db_set("customer", customer, update_modified=False)

	print "updated issue list: ", updated_list

