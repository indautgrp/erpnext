import frappe

def execute():
	updated_list = []

	for je in frappe.db.sql_list("""select name from `tabJournal Entry` where voucher_type='Credit Note' and docstatus < 2"""):
		je = frappe.get_doc("Journal Entry", je)
		original = je.total_amount

		je.set_print_format_fields()

		if je.total_amount != original:
			updated_list.append(je.name)
			je.db_set("total_amount", je.total_amount, update_modified=False)
			je.db_set("total_amount_in_words", je.total_amount_in_words, update_modified=False)

	print "updated jv list: ", updated_list

