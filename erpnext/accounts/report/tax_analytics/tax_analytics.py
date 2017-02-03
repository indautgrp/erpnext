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

	if taxes == "":
		frappe.msgprint(_("No account is set to show in tax report"))
		return [], []

	if filters.accounting == "Accrual Accounting":
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

def get_coa_taxes():
	""" From Chart of Accounts - Should be a tax and the checkbox show_in_tax_reports must be checked """
	coa_taxes = ""
	for ct in frappe.db.sql("select name from tabAccount where show_in_tax_reports = 1"):
		coa_taxes += "'" + ct[0] + "',"

	if coa_taxes != "":
		coa_taxes = "and tabAccount.name in (" + coa_taxes[:len(coa_taxes)-1] + ") "

	return coa_taxes

def get_conditions_accrual_accounting(filters):
	conditions = ""

	if filters.company:
		conditions += " and tabAccount.company = %(company)s"

	if filters.from_date:
		conditions += " and `tabGL Entry`.posting_date >= %(from_date)s"

	if filters.to_date:
		conditions += " and `tabGL Entry`.posting_date <= %(to_date)s"

	return conditions

def get_conditions_cash_accounting(filters):
	conditions = ""
	conditions_payment_entry = ""

	if filters.company:
		conditions += " and tabAccount.company = %(company)s"
		conditions_payment_entry += " and tabAccount.company = %(company)s"

	if filters.from_date:
		conditions += " and `tabJournal Entry`.posting_date between %(from_date)s and %(to_date)s"
		conditions_payment_entry += """ and `tabPayment Entry`.posting_date between %(from_date)s and %(to_date)s"""

	return conditions, conditions_payment_entry

def prepare_data(nodes, filters, conditions, conditions_payment_entry):
	data = []
	grand_total_sale = 0.0
	grand_total_purchase = 0.0
	total_tax_collected = 0.0
	total_tax_paid = 0.0

	# to create a list of invoices and to show invoice's values splitted when it have more than 1 entry showing in the grid 
	split_invoices = []
	multi_invoice = {}

	for n in nodes:
		tax_collected_node = 0.0
		tax_paid_node = 0.0
		grand_total_sale_node = 0.0
		grand_total_purchase_node = 0.0
		indent = 0
		row_node = {
			"date": None,
			"account_name": n.account_name,
			"total_taxes_and_charges": None,
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
		if filters.accounting == "Accrual Accounting":
			value_added_tax = get_tax_total_accrual_accounting(filters, conditions, n.account_head, "")
			total_invoices = get_tax_total_accrual_accounting(filters, conditions, n.account_head, "update_values")
		else:  # Cash Accounting
			value_added_tax = get_tax_total_cash_accounting(filters, conditions, n.account_head, conditions_payment_entry, "")
			total_invoices = get_tax_total_cash_accounting(
				filters, conditions, n.account_head, conditions_payment_entry, "update_values")

		# get a list of all rows in the grid
		for c in value_added_tax:
			split_invoices.append(c.voucher_no)

		for d, t in zip(value_added_tax, total_invoices):

			# get root_type for jv
			if "JV-" in d.voucher_no:
				if root_type[position_root_type] == "Expense":
					t.purchase_value = t.sales_value
					t.sales_value = 0.0
					d.tax_paid = d.tax_collected
					d.tax_collected = 0.0
				position_root_type += 1

			row = {
				"date": d.posting_date,
				"account_name": d.account_name,
				"total_taxes_and_charges": d.total_taxes_and_charges,
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
			"date": None,
			"account_name": n.account_name,
			"total_taxes_and_charges": n.total_taxes_and_charges,
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
		"date": None,
		"account_name": None,
		"total_taxes_and_charges": None,
		"rate": "Grand Total",
		"sales_value": grand_total_sale,
		"purchase_value": grand_total_purchase,
		"tax_collected": total_tax_collected,
		"tax_paid": total_tax_paid,
		"parent_labels": None,
		"indent": indent
	}

	data.append(row_total)

	# count how many times each invoice is shown
	for i in split_invoices:
		if i in multi_invoice:
			multi_invoice[i] += 1
		else:
			multi_invoice[i] = 1

	# update sales/purchase value with value splitted
	for d in data:
		for m in multi_invoice:
			if d["rate"] == m and multi_invoice[m] > 1:
				if d["total_taxes_and_charges"] == 0.0:
					d["purchase_value"] = 0.0
					d["sales_value"] = 0.0
				else:
					d["purchase_value"] = d["purchase_value"] * round(d["tax_paid"] / d["total_taxes_and_charges"], 2)
					d["sales_value"] = d["sales_value"] * round(d["tax_collected"] / d["total_taxes_and_charges"], 2)
				data[data.count(d) - 1]["purchase_value"] = d["purchase_value"]
				data[data.count(d) - 1]["sales_value"] = d["sales_value"]

	position_next_node_rate = 0
	position_node_rate = 0
	pv_gt = 0.0
	sv_gt = 0.0
	update_node_pv = 0.0
	update_node_sv = 0.0

	# update node totals according to the new values
	for d in data:
		if d["indent"] == 0:
			pv_gt += update_node_pv
			sv_gt += update_node_sv
			update_node_pv = 0.0
			update_node_sv = 0.0
			position_node_rate = position_next_node_rate
		else:
			update_node_pv += d["purchase_value"]
			data[position_node_rate]["purchase_value"] = update_node_pv
			update_node_sv += d["sales_value"]
			data[position_node_rate]["sales_value"] = update_node_sv
		position_next_node_rate += 1

	data[position_node_rate]["purchase_value"] = pv_gt
	data[position_node_rate]["sales_value"] = sv_gt

	return data

def get_columns():
	return [
		{
			"fieldname": "date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 75
		},
		{
			"fieldname": "rate",
			"label": _("Rate"),
			"fieldtype": "Data",
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
	""" to check if it is Expense or Income to use as Paid or as Collected """
	sql = frappe.db.sql("""select root_type, concat(voucher_no, ': ', title) as voucher_no
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			where voucher_no in (
				select voucher_no
				from `tabGL Entry`
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabJournal Entry`.name
				where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
				and `tabJournal Entry`.docstatus = 1
				and `tabGL Entry`.account = %(account_head)s
				{conditions}
				and exists(select credit
					from `tabJournal Entry Account`
					left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type
					where `tabJournal Entry Account`.parent = voucher_no and root_type in ('Expense', 'Income'))
				group by voucher_no)
			and root_type in ('Expense', 'Income')
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

def invoices_tax_total_with_no_gl_entries_accrual_accounting(conditions, fields):
	""" to get the amounts of some Sales/Purchase Invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabGL Entry`.", "")

	inv = """UNION ALL
			select {fields}
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabSales Invoice`.base_discount_amount = (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			and account_head = %(account_head)s
			{conditions}
			group by voucher_no
			""".format(conditions=conditions,fields=fields)

	return inv + inv.replace("Sales ", "Purchase ")

def invoices_rates_with_no_gl_entries_accrual_accounting(conditions, taxes):
	""" to get the rates (nodes) of some Sales/Purchase Invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabGL Entry`.", "")

	inv = """UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabSales Invoice`.base_discount_amount = (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			""".format(taxes=taxes,conditions=conditions)

	return inv + inv.replace("Sales ", "Purchase ")

def get_tax_total_accrual_accounting(filters, conditions, account_head, update_total):
	""" to get the amounts of Accrual Accounting for some account """
	if update_total == "":
		sales_fields = """concat(voucher_no, ': ', title) as voucher_no, (tax_amount_after_discount_amount) as tax_collected,
			0.0 as tax_paid, `tabGL Entry`.posting_date, account_name, total_taxes_and_charges"""
		purchase_fields = """concat(voucher_no, ': ', title) as voucher_no, 0.0 as tax_collected,
			sum(tax_amount_after_discount_amount) as tax_paid, `tabGL Entry`.posting_date, account_name, total_taxes_and_charges"""
		jv_fields = """concat(voucher_no, ': ', title) as voucher_no,
			if(`tabGL Entry`.credit_in_account_currency > 0.0, `tabGL Entry`.credit_in_account_currency,
			`tabGL Entry`.debit_in_account_currency) as tax_collected,
			0.0 as tax_paid, `tabJournal Entry`.posting_date, account_name, 0.0 as total_taxes_and_charges"""
		sales_cond = "and root_type = 'Income'"
		purchase_cond = "and tabAccount.account_name = 'Creditors'"
		si_pi_with_no_gl_entries = """concat(`tabSales Invoice`.name, ': ', title) as voucher_no,
			(tax_amount_after_discount_amount) as tax_collected, 0.0 as tax_paid, posting_date, account_name,
			total_taxes_and_charges"""
		jv = """select {jv_fields}
				from `tabGL Entry`
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
				where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
				and `tabGL Entry`.account = %(account_head)s
				and `tabJournal Entry`.docstatus = 1
				and exists(select credit
					from `tabJournal Entry Account`
					left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
					where `tabJournal Entry Account`.parent = voucher_no
					and root_type in ('Expense', 'Income'))
				{conditions}
				group by voucher_no
				""".format(jv_fields=jv_fields,conditions=conditions)
	else:
		sales_fields = """base_grand_total as sales_value, 0.0 as purchase_value, voucher_no, `tabGL Entry`.posting_date,
			account_name, total_taxes_and_charges"""
		purchase_fields = """0.0 as sales_value, base_grand_total as purchase_value, voucher_no, `tabGL Entry`.posting_date,
			account_name, total_taxes_and_charges"""
		jv_fields = """if(`tabJournal Entry Account`.debit_in_account_currency > 0.0,
			sum(`tabJournal Entry Account`.debit_in_account_currency), 0.0) as sales_value,
			0.0 as purchase_value, `tabJournal Entry Account`.parent as voucher_no, `tabJournal Entry`.posting_date, account_name,
			0.0 as total_taxes_and_charges"""
		sales_cond = ""
		purchase_cond = ""
		si_pi_with_no_gl_entries = """base_grand_total as sales_value, 0.0 as purchase_value,
			`tabSales Invoice`.name as voucher_no, posting_date, account_name, total_taxes_and_charges"""
		jv = """select {jv_fields}
				from `tabJournal Entry Account`
			    left join tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
			    left join `tabJournal Entry` ON `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			    where report_type = 'Profit and Loss'
			    and `tabJournal Entry Account`.parent in (
					select voucher_no
					from `tabGL Entry`
					left join tabAccount on tabAccount.name = `tabGL Entry`.account
					left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
					left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
					where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
					and `tabGL Entry`.account = %(account_head)s
					and `tabJournal Entry`.docstatus = 1
					and exists(select credit
						from `tabJournal Entry Account`
						left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
						where `tabJournal Entry Account`.parent = voucher_no
						and root_type in ('Expense', 'Income'))
					{conditions}
					group by voucher_no)
				group by voucher_no
				""".format(jv_fields=jv_fields,conditions=conditions)

	# UNION list (amounts):
	# Sales Invoices
	# Purchase Invoices
	# Journal Entries
	# Sales/Purchase Invoices that don't have gl entries
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
			{jv}
			{invoices_with_no_gl_entries}
			order by posting_date, voucher_no
			""".format(conditions=conditions,
					   purchase_fields=purchase_fields,
					   sales_fields=sales_fields,
					   jv_fields=jv_fields,
					   sales_cond=sales_cond,
					   purchase_cond=purchase_cond,
					   invoices_with_no_gl_entries=invoices_tax_total_with_no_gl_entries_accrual_accounting(
						   conditions, si_pi_with_no_gl_entries),
	                   jv=jv),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

def get_rates_accrual_accounting(filters, conditions, taxes):
	""" to get the rates (nodes) of Accrual Accounting """
	# UNION list (rates/nodes):
	# Sales Invoices
	# Purchase Invoices
	# Journal Entries
	# Sales/Purchase Invoices that don't have gl entries
	return frappe.db.sql("""
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			where `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabGL Entry`.voucher_no
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
			and `tabGL Entry`.docstatus = 1
			and exists(select root_type
				 from `tabJournal Entry Account`
				 left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				 where `tabJournal Entry Account`.parent = voucher_no
				 and root_type in ('Expense', 'Income'))
			{taxes}
			{conditions}
			group by node_rate, account_head
			{invoices_with_no_gl_entries}
			order by rate, account_head
			""".format(taxes=taxes, 
	                   conditions=conditions,
	                   invoices_with_no_gl_entries=invoices_rates_with_no_gl_entries_accrual_accounting(conditions, taxes)),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)

###################
# CASH ACCOUNTING #
###################

def invoices_tax_total_with_no_gl_entries_cash_accounting(conditions, conditions_payment_entry, fields):
	""" to get the amounts of some invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabJournal Entry`.posting_date", "`tabSales Invoice`.posting_date")

	inv = """UNION ALL
			select {fields}
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = `tabSales Invoice`.name
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where `tabSales Invoice`.base_discount_amount =  (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			and account_head = %(account_head)s
			{conditions}
			group by voucher_no
			""".format(fields=fields,conditions=conditions)

	inv_new_pay = """UNION ALL
			select {fields}
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = `tabSales Invoice`.name
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where `tabSales Invoice`.base_discount_amount =  (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			and account_head = %(account_head)s
			{conditions_payment_entry}
			group by voucher_no
			""".format(fields=fields,conditions_payment_entry=conditions_payment_entry)

	return inv + inv.replace("Sales ", "Purchase ") + inv_new_pay + inv_new_pay.replace("Sales ", "Purchase ")

def invoices_rates_with_no_gl_entries_cash_accounting(conditions, conditions_payment_entry, taxes):
	""" to get the rates (nodes) of some invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabJournal Entry`.posting_date", "`tabSales Invoice`.posting_date")

	inv = """UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = `tabSales Invoice`.name
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where `tabSales Invoice`.base_discount_amount =  (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			""".format(taxes=taxes,conditions=conditions)

	inv_new_pay = """UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = `tabSales Invoice`.name
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where `tabSales Invoice`.base_discount_amount =  (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			{taxes}
			{conditions_payment_entry}
		    group by node_rate, account_head
			""".format(taxes=taxes,conditions_payment_entry=conditions_payment_entry)

	return inv + inv.replace("Sales ", "Purchase ") + inv_new_pay + inv_new_pay.replace("Sales ", "Purchase ")

def get_tax_total_cash_accounting(filters, conditions, account_head, conditions_payment_entry, update_total):
	""" to get the amounts of Cash Accounting for some account """
	if update_total == "":
		sales_fields = """concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no,
            (`tabJournal Entry Account`.credit_in_account_currency / `tabSales Invoice`.base_grand_total)
            * tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid, `tabJournal Entry`.posting_date, account_name,
            total_taxes_and_charges"""
		sales_fields_new_payment = """concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no,
			(allocated_amount  / `tabSales Invoice`.base_grand_total) *	tax_amount_after_discount_amount as tax_collected,
			0.0 as tax_paid, `tabPayment Entry`.posting_date, account_name, total_taxes_and_charges"""
		purchase_fields = """concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected,
			(`tabJournal Entry Account`.debit_in_account_currency / `tabPurchase Invoice`.base_grand_total)
			* tax_amount_after_discount_amount as tax_paid, `tabJournal Entry`.posting_date, account_name,
			total_taxes_and_charges"""
		purchase_fields_new_payment = """concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected,
			(allocated_amount / `tabPurchase Invoice`.base_grand_total) * tax_amount_after_discount_amount as tax_paid,
			`tabPayment Entry`.posting_date, account_name, total_taxes_and_charges"""
		jv_fields = """concat(voucher_no, ': ', title) as voucher_no, if(`tabGL Entry`.credit_in_account_currency > 0.0,
			`tabGL Entry`.credit_in_account_currency, `tabGL Entry`.debit_in_account_currency) as tax_collected,
			0.0 as tax_paid, `tabJournal Entry`.posting_date, account_name, 0.0 as total_taxes_and_charges"""
		sales_cond = "and root_type = 'Income'"
		purchase_cond = "and tabAccount.account_name = 'Creditors'"
		si_pi_with_no_gl_entries = """concat(`tabSales Invoice`.name, ': ', `tabSales Invoice`.title) as voucher_no,
			(tax_amount_after_discount_amount) as tax_collected, 0.0 as tax_paid, `tabSales Invoice`.posting_date, account_name,
			total_taxes_and_charges"""
		jv = """select {jv_fields}
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry') 
			and `tabGL Entry`.account = %(account_head)s
			and `tabJournal Entry`.docstatus = 1
			and exists(select credit
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				where `tabJournal Entry Account`.parent = voucher_no and root_type in ('Expense', 'Income'))
			{conditions}
			group by voucher_no
			""".format(jv_fields=jv_fields,conditions=conditions)
	else:
		sales_fields = """`tabJournal Entry Account`.credit_in_account_currency as sales_value, 0.0 as purchase_value, voucher_no,
			`tabJournal Entry`.posting_date, account_name, total_taxes_and_charges"""
		sales_fields_new_payment = """allocated_amount as sales_value, 0.0 as purchase_value, voucher_no,
			`tabPayment Entry`.posting_date, account_name, total_taxes_and_charges"""
		purchase_fields = """0.0 as sales_value, `tabJournal Entry Account`.debit_in_account_currency as purchase_value, voucher_no,
			`tabJournal Entry`.posting_date, account_name, total_taxes_and_charges"""
		purchase_fields_new_payment = """0.0 as sales_value, allocated_amount as purchase_value, voucher_no,
			`tabPayment Entry`.posting_date, account_name, total_taxes_and_charges"""
		jv_fields = """if(`tabJournal Entry Account`.debit_in_account_currency > 0.0,
			sum(`tabJournal Entry Account`.debit_in_account_currency), 0.0) as sales_value,
			0.0 as purchase_value, `tabJournal Entry Account`.parent as voucher_no, `tabJournal Entry`.posting_date, account_name,
			0.0 as total_taxes_and_charges"""
		sales_cond = ""
		purchase_cond = ""
		si_pi_with_no_gl_entries = """base_grand_total as sales_value, 0.0 as purchase_value, `tabSales Invoice`.name as voucher_no,
			`tabSales Invoice`.posting_date, account_name, total_taxes_and_charges"""
		jv = """select {jv_fields}
			from `tabJournal Entry Account`
		    left join tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
		    left join `tabJournal Entry` ON `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		    where report_type = 'Profit and Loss'
		    and `tabJournal Entry Account`.parent in (
				select voucher_no
				from `tabGL Entry`
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
				where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
				and `tabGL Entry`.account = %(account_head)s
				and `tabJournal Entry`.docstatus = 1
				and exists(select credit
					from `tabJournal Entry Account`
					left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
					where `tabJournal Entry Account`.parent = voucher_no and root_type in ('Expense', 'Income'))
				{conditions}
				group by voucher_no)
			group by voucher_no
			""".format(jv_fields=jv_fields,conditions=conditions)

	# UNION list (amounts):
	# Sales Invoices
	# Sales Invoices with new payment entry
	# Purchase Invoices
	# Purchase Invoices with new payment entry
	# Journal Entries
	# Sales/Purchase Invoices that don't have gl entries
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
			and `tabJournal Entry Account`.parent in (select `tabJournal Entry Account`.parent
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				where `tabJournal Entry Account`.docstatus = 1
				{conditions}
				and tabAccount.account_type in ('Bank', 'Cash'))
			{conditions}
			{sales_cond}
			group by `tabJournal Entry Account`.parent
			UNION ALL
			select {sales_fields_new_payment}
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabSales Invoice`.docstatus = 1
			and `tabPayment Entry`.docstatus = 1
			{conditions_payment_entry}
			{sales_cond}
			group by `tabPayment Entry Reference`.parent
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
			and `tabJournal Entry Account`.parent in (select `tabJournal Entry Account`.parent
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				where `tabJournal Entry Account`.docstatus = 1
				{conditions}
				and tabAccount.account_type in ('Bank', 'Cash'))
			{conditions}
			{purchase_cond}
			group by `tabJournal Entry Account`.parent
			UNION ALL
			select {purchase_fields_new_payment}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabPurchase Invoice`.docstatus = 1
			and `tabPayment Entry`.docstatus = 1
			{conditions_payment_entry}
			{purchase_cond}
			group by `tabPayment Entry Reference`.parent
			UNION ALL
			{jv}
			{invoices_with_no_gl_entries}
			order by posting_date, voucher_no
			""".format(conditions=conditions,
					   conditions_payment_entry=conditions_payment_entry,
					   sales_fields=sales_fields,
					   sales_fields_new_payment=sales_fields_new_payment,
					   purchase_fields=purchase_fields,
					   purchase_fields_new_payment=purchase_fields_new_payment,
					   jv_fields=jv_fields,
					   sales_cond=sales_cond,
					   purchase_cond=purchase_cond,
					   invoices_with_no_gl_entries=invoices_tax_total_with_no_gl_entries_cash_accounting(
						   conditions, conditions_payment_entry, si_pi_with_no_gl_entries),
	                   jv=jv),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

def get_rates_cash_accounting(filters, conditions, conditions_payment_entry, taxes):
	""" to get the rates (nodes) of Cash Accounting """
	# UNION list (rates/nodes):
	# Sales Invoices
	# Sales Invoices with new payment entry
	# Purchase Invoices
	# Purchase Invoices with new payment entry
	# Journal Entries
	# Sales/Purchase Invoices that don't have gl entries
	return frappe.db.sql("""
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions_payment_entry}
			group by node_rate, account_head
			UNION 
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			where `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions_payment_entry}
			group by node_rate, account_head
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabJournal Entry`.name
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
			and exists(select root_type
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				where `tabJournal Entry Account`.parent = voucher_no
				and root_type in ('Expense', 'Income'))
			and `tabGL Entry`.docstatus = 1
			{taxes}
			{conditions}
			group by node_rate, account_head
			{invoices_with_no_gl_entries}
			order by rate, account_head
			""".format(taxes=taxes,
					   conditions=conditions,
					   conditions_payment_entry=conditions_payment_entry,
					   invoices_with_no_gl_entries=invoices_rates_with_no_gl_entries_cash_accounting(
						   conditions, conditions_payment_entry, taxes)),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)