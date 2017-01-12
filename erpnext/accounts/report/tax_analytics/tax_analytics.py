# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from datetime import datetime
from erpnext.accounts.report.accounts_receivable.accounts_receivable import get_ageing_data
from frappe.utils import getdate, flt
from frappe.utils.pdf import get_pdf

def execute(filters=None):
	if not filters: filters = {}

	validate_date_range(filters)
	columns = get_columns()
	taxes = get_coa_taxes()

	if (filters.accounting == "Accrual Accounting"):
		data = get_data_accrual_accounting(filters, taxes)
	else: # Cash Accounting
		data = get_data_cash_accounting(filters, taxes)

	return columns, data

def validate_date_range(filters):
	dates = filters.date_range.split(" ")
	if dates:
		filters.from_date = datetime.strptime(dates[0], '%d-%m-%Y').strftime('%Y-%m-%d')
		filters.to_date = datetime.strptime(dates[2], '%d-%m-%Y').strftime('%Y-%m-%d')
		del filters["date_range"]

def get_data_accrual_accounting(filters, taxes):
	conditions = get_conditions_accrual_accounting(filters)
	nodes = get_rates_accrual_accounting(filters, conditions, taxes)
	data = prepare_data(nodes, filters, conditions, "")

	return data

def get_data_cash_accounting(filters, taxes):
	conditions, conditions_payment_entry = get_conditions_cash_accounting(filters)
	nodes = get_rates_cash_accounting(filters, conditions, conditions_payment_entry, taxes)
	data = prepare_data(nodes, filters, conditions, conditions_payment_entry)

	return data

# From Chart of Accounts - Should be a tax and the checkbox show_in_tax_reports must be checked
def get_coa_taxes():
	coa_taxes = ""
	for ct in frappe.db.sql("select name from tabAccount where show_in_tax_reports = 1"):
		coa_taxes += "'" + ct[0] + "',"

	if coa_taxes != "":
		coa_taxes = "and tabAccount.name in (" + coa_taxes[:len(coa_taxes)-1] + ") "

	return coa_taxes

def get_conditions_accrual_accounting(filters):
	conditions = ""

	if (filters.company):
		conditions += " and tabAccount.company = %(company)s"

	if (filters.from_date):
		conditions += " and `tabGL Entry`.posting_date >= %(from_date)s"

	if (filters.to_date):
		conditions += " and `tabGL Entry`.posting_date <= %(to_date)s"

	return conditions

def get_conditions_cash_accounting(filters):
	conditions = ""
	conditions_payment_entry = ""

	if (filters.company):
		conditions += " and tabAccount.company = %(company)s"
		conditions_payment_entry += " and tabAccount.company = %(company)s"

	if (filters.from_date):
		conditions += " and `tabJournal Entry`.posting_date between %(from_date)s and %(to_date)s"
		conditions_payment_entry += """ and `tabPayment Entry`.reference_date between %(from_date)s and %(to_date)s"""

	return conditions, conditions_payment_entry

def prepare_data(nodes, filters, conditions, conditions_payment_entry):
	data = []
	grand_total_sale = 0.0
	grand_total_purchase = 0.0
	total_tax_collected = 0.0
	total_tax_paid = 0.0

	for n in nodes:
		tax_collected_node = 0.0
		tax_paid_node = 0.0
		grand_total_sale_node = 0.0
		grand_total_purchase_node = 0.0
		indent = 0
		row_node = {
			"rate": n.node_rate,
			"sales_value": None,
			"purchase_value": None,
			"tax_collected": None,
			"tax_paid": None,
			"parent_labels": None,
			"indent": indent
		}

		data.append(row_node)

		position_node = len(data)
		indent = 1

		root_type = get_jv_account_type(filters, conditions, n.account_head)
		position_root_type = 0
		if (filters.accounting == "Accrual Accounting"):
			gst_tax = get_tax_total_accrual_accounting(filters, conditions, n.account_head, "")
			total_invoices = get_tax_total_accrual_accounting(filters, conditions, n.account_head, "update_values")
		else:  # Cahs Accounting
			gst_tax = get_tax_total_cash_accounting(filters, conditions, n.account_head, conditions_payment_entry, "")
			total_invoices = get_tax_total_cash_accounting(filters, conditions, n.account_head, conditions_payment_entry, "update_values")

		for d, t in zip(gst_tax, total_invoices):

			# get root_type for jv
			if ("JV-" in d.voucher_no):
				if root_type[position_root_type] == "Expense":
					t.purchase_value = t.sales_value
					t.sales_value = 0.0
					d.tax_paid = d.tax_collected
					d.tax_collected = 0.0
				position_root_type += 1

			# # don't show negative values
			# if not (d.tax_collected >= 0.0 and d.tax_paid >= 0.0):
			# 	continue

			# 0% tax account is 0% tax
			if (n.rate == 0.0):
				d.tax_collected = 0.0
				d.tax_paid = 0.0

			row = {
				"rate": d.voucher_no,
				"sales_value": t.sales_value,
				"purchase_value": t.purchase_value,
				"tax_collected": d.tax_collected,
				"tax_paid": d.tax_paid,
				"parent_labels": n.node_rate,
				"indent": indent
			}

			data.append(row)

			# total in each node
			tax_collected_node += d.tax_collected
			tax_paid_node += d.tax_paid
			grand_total_sale_node += t.sales_value
			grand_total_purchase_node += t.purchase_value

		# update total in each node line
		data[position_node - 1] = {
			"tax_collected": tax_collected_node,
			"tax_paid": tax_paid_node,
			"sales_value": grand_total_sale_node,
			"purchase_value": grand_total_purchase_node,
			"parent_labels": None,
			"rate": n.node_rate,
			"indent": indent - 1
		}

		# grand total line
		total_tax_collected += tax_collected_node
		total_tax_paid += tax_paid_node
		grand_total_sale += grand_total_sale_node
		grand_total_purchase += grand_total_purchase_node

	indent = 0
	row_total = {
		"rate": "Grand Total",
		"sales_value": grand_total_sale,
		"purchase_value": grand_total_purchase,
		"tax_collected": total_tax_collected,
		"tax_paid": total_tax_paid,
		"parent_labels": None,
		"indent": indent
	}

	data.append(row_total)

	return data

def get_columns():
	return [
		{
			"fieldname": "rate",
			"label": _("Rate"),
			"fieldtype": "Data",
			"options": "Account",
			"width": 300
		},
		{
			"fieldname": "sales_value",
			"label": _("Sales Value"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120
		},
		{
			"fieldname": "purchase_value",
			"label": _("Purchase Value"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120
		},
		{
			"fieldname": "tax_collected",
			"label": _("Tax Collected"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120
		},
		{
			"fieldname": "tax_paid",
			"label": _("Tax Paid"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120
		}
	]

def get_jv_account_type(filters, conditions, account_head):

	sql = frappe.db.sql("""select root_type, concat(voucher_no, ': ', title) as voucher_no
			FROM `tabGL Entry`
			LEFT JOIN tabAccount ON tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			where voucher_no IN (
				SELECT voucher_no
				FROM `tabGL Entry`
				LEFT JOIN tabAccount ON tabAccount.name = `tabGL Entry`.account
				LEFT JOIN `tabJournal Entry` ON `tabJournal Entry`.name = `tabGL Entry`.voucher_no
				LEFT JOIN `tabJournal Entry Account` ON `tabJournal Entry Account`.parent = `tabJournal Entry`.name
				WHERE `tabGL Entry`.voucher_type IN ('Journal Entry', 'Payment Entry')
				AND `tabJournal Entry`.docstatus = 1
				AND `tabGL Entry`.account = %(account_head)s
				{conditions}
				AND exists(SELECT credit
					FROM `tabJournal Entry Account`
					LEFT JOIN tabAccount ON tabAccount.account_type = `tabJournal Entry Account`.account_type
					WHERE `tabJournal Entry Account`.parent = voucher_no AND root_type IN ('Expense', 'Income'))
				GROUP BY voucher_no)
			and root_type IN ('Expense', 'Income')
			and `tabJournal Entry`.docstatus = 1
			group by voucher_no
			order by `tabGL Entry`.posting_date, voucher_no
			""".format(conditions=conditions),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

	invoice = 0
	root_type = {}
	for x in sql:
		root_type[invoice] = x.get("root_type")
		invoice += 1

	return root_type

######################
# ACCRUAL ACCOUNTING #
######################

def get_tax_total_accrual_accounting(filters, conditions, account_head, update_total):
	if update_total == "":
		sales_fields = " concat(voucher_no, ': ', title) as voucher_no, (tax_amount_after_discount_amount) as tax_collected, 0.0 as tax_paid, `tabGL Entry`.posting_date "
		purchase_fields = " concat(voucher_no, ': ', title) as voucher_no, 0.0 as tax_collected, sum(tax_amount_after_discount_amount) as tax_paid, `tabGL Entry`.posting_date "
		jv_fields = """ concat(voucher_no, ': ', title) as voucher_no,
					case when `tabGL Entry`.credit_in_account_currency > 0.0 then `tabGL Entry`.credit_in_account_currency else `tabGL Entry`.debit_in_account_currency end as tax_collected,
					0.0 as tax_paid, `tabGL Entry`.posting_date"""
		sales_cond = " and root_type = 'Income'"
		purchase_cond = " and tabAccount.account_name = 'Creditors'"
		jv_join = " left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no"
	else:
		sales_fields = " base_grand_total as sales_value, 0.0 as purchase_value, voucher_no, `tabGL Entry`.posting_date"
		purchase_fields = " 0.0 as sales_value, base_grand_total as purchase_value, voucher_no, `tabGL Entry`.posting_date"
		jv_fields = """ case when total_debit > 0.0 then total_debit else 0.0 end as sales_value,
					0.0 as purchase_value, 
					voucher_no, `tabGL Entry`.posting_date"""
		sales_cond = ""
		purchase_cond = ""
		jv_join = " left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabJournal Entry`.name"

	return frappe.db.sql("""
			select {sales_fields}
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabSales Invoice`.docstatus = 1
			{conditions}
			{sales_cond}
			group by voucher_no
			UNION ALL 
			select {purchase_fields}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabPurchase Invoice`.docstatus = 1
			{conditions}
			{purchase_cond}
			group by voucher_no
			UNION ALL 
			select {jv_fields}
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			{jv_join}
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
			and `tabGL Entry`.account = %(account_head)s
			and `tabJournal Entry`.docstatus = 1
			and exists(select credit 
				from `tabJournal Entry Account` 
				left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type 
				where `tabJournal Entry Account`.parent = voucher_no and root_type in ('Expense', 'Income'))
			{conditions}
			group by voucher_no
			order by posting_date, voucher_no
			""".format(conditions=conditions,
					   purchase_fields=purchase_fields,
					   sales_fields=sales_fields,
					   jv_fields=jv_fields,
					   sales_cond=sales_cond,
					   purchase_cond=purchase_cond,
					   jv_join=jv_join),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

def get_rates_accrual_accounting(filters, conditions, taxes):
	return frappe.db.sql("""
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			where `tabGL Entry`.voucher_type in ('Purchase Invoice')
			{taxes}
			{conditions}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
			from `tabGL Entry`			
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabGL Entry`.voucher_type in ('Sales Invoice')
			{taxes}
			{conditions}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabGL Entry`.voucher_no
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
			and exists(SELECT root_type
				 FROM `tabJournal Entry Account`
					 LEFT JOIN tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
				 WHERE root_type IN ('Expense', 'Income'))
			{taxes}
			{conditions}
			group by node_rate, account_head
			order by rate asc
			""".format(taxes=taxes, conditions=conditions),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)

###################
# CASH ACCOUNTING #
###################

def get_tax_total_cash_accounting(filters, conditions, account_head, conditions_payment_entry, update_total):
	if update_total == "":
		sales_fields = " concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no, (tax_amount_after_discount_amount) as tax_collected, 0.0 as tax_paid, `tabGL Entry`.posting_date "
		purchase_fields = " concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected, sum(tax_amount_after_discount_amount) as tax_paid, `tabGL Entry`.posting_date "
		jv_fields = """ concat(voucher_no, ': ', title) as voucher_no,
					case when `tabGL Entry`.credit_in_account_currency > 0.0 then `tabGL Entry`.credit_in_account_currency else `tabGL Entry`.debit_in_account_currency end as tax_collected,
					0.0 as tax_paid, `tabGL Entry`.posting_date"""
		sales_cond = " and root_type = 'Income'"
		purchase_cond = " and tabAccount.account_name = 'Creditors'"
		jv_join = " left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no"
	else:
		sales_fields = " base_grand_total as sales_value, 0.0 as purchase_value, voucher_no, `tabGL Entry`.posting_date"
		purchase_fields = " 0.0 as sales_value, base_grand_total as purchase_value, voucher_no, `tabGL Entry`.posting_date"
		jv_fields = """ case when total_debit > 0.0 then total_debit else 0.0 end as sales_value,
					0.0 as purchase_value, 
					voucher_no, `tabGL Entry`.posting_date"""
		sales_cond = ""
		purchase_cond = ""
		jv_join = " left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabJournal Entry`.name"

	return frappe.db.sql("""
			select {sales_fields}
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabSales Invoice`.docstatus = 1
			{conditions}
			{sales_cond}
			group by voucher_no
			UNION ALL
			select {sales_fields}
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabSales Invoice`.docstatus = 1
			{conditions_payment_entry}
			{sales_cond}
			group by voucher_no
			UNION ALL
			select {purchase_fields}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabPurchase Invoice`.docstatus = 1
			{conditions}
			{purchase_cond}
			group by voucher_no
			UNION ALL
			select {purchase_fields}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabPurchase Invoice`.docstatus = 1
			{conditions_payment_entry}
			{purchase_cond}
			group by voucher_no
			UNION ALL
			select {jv_fields}
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			{jv_join}
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry') 
			and `tabGL Entry`.account = %(account_head)s
			and `tabJournal Entry`.docstatus = 1
			and exists(select credit 
				from `tabJournal Entry Account` 
				left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type 
				where `tabJournal Entry Account`.parent = voucher_no and root_type in ('Expense', 'Income'))
			{conditions}
			group by voucher_no
			order by posting_date, voucher_no
				""".format(conditions=conditions,
						   conditions_payment_entry=conditions_payment_entry,
						   sales_fields=sales_fields,
						   purchase_fields=purchase_fields,
						   jv_fields=jv_fields,
						   sales_cond=sales_cond,
						   purchase_cond=purchase_cond,
						   jv_join=jv_join),
					{
						"company": filters.company,
						"from_date": filters.from_date,
						"to_date": filters.to_date,
						"account_head": account_head
					}, as_dict=True)

def get_rates_cash_accounting(filters, conditions, conditions_payment_entry, taxes):
	return frappe.db.sql("""
				select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
				from `tabGL Entry`
				left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				where `tabGL Entry`.voucher_type in ('Sales Invoice')
				{taxes}
				{conditions}
				group by node_rate, account_head
				UNION
				select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
				from `tabGL Entry`
				left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
				left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
				where `tabGL Entry`.voucher_type in ('Sales Invoice')
				{taxes}
				{conditions_payment_entry}
				group by node_rate, account_head
				UNION 
				select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
				from `tabGL Entry`
				left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				where `tabGL Entry`.voucher_type in ('Purchase Invoice')
				{taxes}
				{conditions}
				group by node_rate, account_head
				UNION
				select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
				from `tabGL Entry`
				left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
				left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
				where `tabGL Entry`.voucher_type in ('Purchase Invoice')
				{taxes}
				{conditions_payment_entry}
				group by node_rate, account_head
				UNION 
				select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate, tabAccount.name as account_head
				from `tabGL Entry`
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabJournal Entry`.name
				where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
				and exists(SELECT root_type
					FROM `tabJournal Entry Account`
					LEFT JOIN tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
					WHERE root_type IN ('Expense', 'Income'))
				{taxes}
				{conditions}
				group by node_rate, account_head
				order by rate asc
				""".format(taxes=taxes,
						   conditions=conditions,
						   conditions_payment_entry=conditions_payment_entry),
					{
						"company": filters.company,
						"from_date": filters.from_date,
						"to_date": filters.to_date
					}, as_dict=True)