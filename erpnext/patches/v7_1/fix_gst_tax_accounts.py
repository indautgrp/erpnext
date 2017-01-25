from __future__ import unicode_literals
import frappe
from frappe import _

def execute():
	create_gst_accounts()
	update_fields_account_imports()
	update_fields_account_exports()
	udate_fields_jv_capital_on_acquisitions()

def create_gst_accounts():
	if not frappe.db.exists('Account', {'account_name': 'GST Adjustments'}):
		make_gst("GST Adjustments", 0)
	if not frappe.db.exists('Account', {'account_name': 'GST on Capital Acquisitions'}):
		make_gst("GST on Capital Acquisitions", 10)
	if not frappe.db.exists('Account', {'account_name': 'GST on Exports'}):
		make_gst("GST on Exports", 0)
	if not frappe.db.exists('Account', {'account_name': 'GST on Imports'}):
		make_gst("GST on Imports", 0)

def make_gst(account_name, tax_rate):
	gst = frappe.get_doc({
		"doctype": "Account",
		"account_name": account_name,
		"is_group": 0,
		"root_type": "Liability",
		"account_type": "Tax",
		"account_currency": "AUD",
		"company": "Industrial Automation Group Pty Ltd",
		"tax_rate": tax_rate,
		"report_type": "Balance Sheet",
		"parent": "ATO Liabilities - IAG",
		"parent_account": "ATO Liabilities - IAG",
		"group_or_ledger": "Ledger",
		"old_parent": "ATO Liabilities - IAG",
		"credit_limit": 0,
		"credit_days": 0,
		"show_in_tax_reports": 1
	})
	gst.insert(ignore_permissions=True)

# Supplier not from Australia
def update_fields_account_imports():
	suppliers_invoices = """(select `tabPurchase Invoice`.name as PINV
							from `tabPurchase Invoice` 
							left join tabSupplier on tabSupplier.name = `tabPurchase Invoice`.supplier
							where currency <> 'AUD')"""

	frappe.db.sql("""UPDATE `tabPurchase Taxes and Charges`
				  SET account_head = 'GST on Imports - IAG'
				  WHERE account_head like 'GST Paid - IAG'
				  AND parent in {suppliers_invoices}""".format(suppliers_invoices=suppliers_invoices),{}, as_dict=True)

	frappe.db.sql("""update `tabGL Entry`
				  set account = 'GST on Imports - IAG'
				  where account like 'GST Paid - IAG'
				  and voucher_no in {suppliers_invoices}""".format(suppliers_invoices=suppliers_invoices),{}, as_dict=True)

# Customer not from Australia
def update_fields_account_exports():
	customers_invoices = """(select `tabSales Invoice`.name as SINV
							from `tabSales Invoice` 
							left join tabCustomer on tabCustomer.name = `tabSales Invoice`.customer
							where tabCustomer.territory = 'Rest of the World')"""

	frappe.db.sql("""UPDATE `tabSales Taxes and Charges`
				  SET account_head = 'GST on Exports - IAG'
				  WHERE account_head like 'GST Collected - IAG'
				  AND parent in {customers_invoices}""".format(customers_invoices=customers_invoices),{}, as_dict=True)

	frappe.db.sql("""update `tabGL Entry`
				  set account = 'GST on Exports - IAG'
				  where account like 'GST Collected - IAG'
				  and voucher_no in {customers_invoices}""".format(customers_invoices=customers_invoices),{}, as_dict=True)

# GST on Capital Acquisitions
def udate_fields_jv_capital_on_acquisitions():
	for d in frappe.db.sql("select parent from `tabJournal Entry Account` where account = 'Motor Vehicles GST paid - IAG'"):
		frappe.db.sql("update `tabJournal Entry Account` "
					  "set account = 'GST on Capital Acquisitions - IAG' "
					  "where account = 'GST Paid - IAG' "
					  "and parent = %s", d[0])

		frappe.db.sql("update `tabGL Entry` "
					  "set account = 'GST on Capital Acquisitions - IAG' "
					  "where account = 'GST Paid - IAG' "
					  "and voucher_no = %s", d[0])