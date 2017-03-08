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
	data = prepare_data(nodes, filters, conditions, taxes, conditions_payment_entry="", conditions_date_gl="")

	return data

def get_data_cash_accounting(filters, taxes):
	conditions, conditions_payment_entry, conditions_date_gl = get_conditions_cash_accounting(filters)
	nodes = get_rates_cash_accounting(filters, conditions, conditions_payment_entry, conditions_date_gl, taxes)
	data = prepare_data(nodes, filters, conditions, taxes, conditions_payment_entry, conditions_date_gl)

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
	conditions = ""                 # posting_date from `tabJournal Entry`
	conditions_payment_entry = ""   # posting_date from `tabPayment Entry`
	conditions_date_gl = ""         # posting_date from `tabGL Entry`

	if filters.company:
		conditions += " and tabAccount.company = %(company)s"
		conditions_payment_entry += " and tabAccount.company = %(company)s"
		conditions_date_gl += " and tabAccount.company = %(company)s"

	if filters.from_date:
		conditions += " and `tabJournal Entry`.posting_date between %(from_date)s and %(to_date)s"
		conditions_payment_entry += """ and `tabPayment Entry`.posting_date between %(from_date)s and %(to_date)s"""
		conditions_date_gl += " and `tabGL Entry`.posting_date between %(from_date)s and %(to_date)s"

	return conditions, conditions_payment_entry, conditions_date_gl

def prepare_data(nodes, filters, conditions, taxes, conditions_payment_entry, conditions_date_gl):
	""" to prepare the data fields to be shown in the grid """
	data = []
	grand_total_sale = 0.0
	grand_total_purchase = 0.0
	total_tax_collected = 0.0
	total_tax_paid = 0.0

	# to create a list of invoices and to show invoice's values splitted when it have more than 1 entry showing in the grid 
	split_invoices = []
	multi_invoice = {}

	# fix $ simbol when switching between dt/reports
	company_currency = frappe.db.get_value("Company", filters.company, "default_currency")

	for n in nodes:
		tax_collected_node = 0.0
		tax_paid_node = 0.0
		grand_total_sale_node = 0.0
		grand_total_purchase_node = 0.0
		indent = 1
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
			"indent": indent,
			"currency": company_currency
		}

		data.append(row_node)

		# to update totals in each node line
		position_node = len(data)
		indent = 2

		if filters.accounting == "Accrual Accounting":
			value_added_tax = sorted(get_sinv_tax_total_accrual_accounting(filters, conditions, n.account_head) +
		                         get_pinv_tax_total_accrual_accounting(filters, conditions, n.account_head) +
		                         get_jv_tax_total_accrual(filters, conditions, n.account_head), key=lambda k: k['posting_date'])
		else: # Cash Accounting
			value_added_tax = sorted(get_tax_total_cash_accounting(filters, conditions, n.account_head, conditions_payment_entry,
			                         conditions_date_gl, taxes) +
			                         get_jv_tax_total_cash(filters, conditions, n.account_head), key=lambda k: k['posting_date'])

		# get a list of all rows in the grid
		for c in value_added_tax:
			split_invoices.append(c.voucher_no)

		for d in value_added_tax:
			# root_type for jv and to show correct values
			if "JV-" in d.voucher_no:
				if d.root_type == "Expense":
					if d.tax_paid < 0 and d.purchase_value > 0:
						d.purchase_value *= -1
					d.sales_value = 0.0
					d.tax_collected = 0.0
				else:
					if d.tax_collected < 0 and d.sales_value > 0:
						d.sales_value *= -1
					d.purchase_value = 0.0
					d.tax_paid = 0.0

			row = {
				"date": d.posting_date,
				"account_name": d.account_name,
				"total_taxes_and_charges": d.total_taxes_and_charges,
				"rate": d.voucher_no,
				"sales_value": d.sales_value,
				"purchase_value": d.purchase_value,
				"tax_collected": d.tax_collected,
				"tax_paid": d.tax_paid,
				"grand_total": d.grand_total,
				"base_tax_amount_after_discount_amount": d.base_tax_amount_after_discount_amount,
				"parent_labels": n.node_rate,
				"indent": indent,
				"currency": company_currency
			}

			data.append(row)

			# total in each node
			tax_collected_node += d.tax_collected
			tax_paid_node += d.tax_paid
			grand_total_sale_node += d.sales_value
			grand_total_purchase_node += d.purchase_value

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
			"indent": indent - 1,
			"currency": company_currency
		}

		# grand total line
		total_tax_collected += tax_collected_node
		total_tax_paid += tax_paid_node
		grand_total_sale += grand_total_sale_node
		grand_total_purchase += grand_total_purchase_node

	indent = 1
	# grand total line
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
		"indent": indent,
		"currency": company_currency
	}

	data.append(row_total)

	# to count how many times each invoice is shown
	for i in split_invoices:
		if i in multi_invoice:
			multi_invoice[i] += 1
		else:
			multi_invoice[i] = 1

	# update sales/purchase value with value splitted
	have_multi_invoices = 0
	for d in data:
		for m in multi_invoice:
			if d["rate"] == m and multi_invoice[m] > 1:
				have_multi_invoices = 1
				if d["total_taxes_and_charges"] == 0.0:
					if d["tax_paid"] != 0.0 and d["base_tax_amount_after_discount_amount"] != 0.0:
						d["purchase_value"] = 0.0
						d["sales_value"] = 0.0
					else:
						d["purchase_value"] = d["purchase_value"]
				else:
					if d["purchase_value"] == d["grand_total"]:
						d["purchase_value"] = d["purchase_value"] * (d["tax_paid"] / d["base_tax_amount_after_discount_amount"])
						d["sales_value"] = d["sales_value"] * (d["tax_collected"] / d["base_tax_amount_after_discount_amount"])
					else:
						d["purchase_value"] = d["grand_total"] * (d["tax_paid"] / d["base_tax_amount_after_discount_amount"])
						d["sales_value"] = d["grand_total"] * (d["tax_collected"] / d["base_tax_amount_after_discount_amount"])
				data[data.count(d) - 1]["purchase_value"] = d["purchase_value"]
				data[data.count(d) - 1]["sales_value"] = d["sales_value"]

	if have_multi_invoices == 1:
		position_next_node_rate = 0
		position_node_rate = 0
		purchase_value_grand_total = 0.0
		sales_value_grand_total = 0.0
		update_node_pv = 0.0
		update_node_sv = 0.0

		# update node totals according to the new values
		for d in data:
			if d["indent"] == 1:
				purchase_value_grand_total += update_node_pv
				sales_value_grand_total += update_node_sv
				update_node_pv = 0.0
				update_node_sv = 0.0
				position_node_rate = position_next_node_rate
			else:
				update_node_pv += d["purchase_value"]
				data[position_node_rate]["purchase_value"] = update_node_pv
				update_node_sv += d["sales_value"]
				data[position_node_rate]["sales_value"] = update_node_sv
			position_next_node_rate += 1

		data[position_node_rate]["purchase_value"] = purchase_value_grand_total
		data[position_node_rate]["sales_value"] = sales_value_grand_total

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

def get_cond_invoice_with_no_income_expense(field):
	""" to get invoices with no income or expense account """
	return """and exists (select voucher_no from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			where voucher_no = {field}
			and (root_type in ('Expense', 'Income') or tabAccount.account_type = 'Stock Received But Not Billed'))
			""".format(field=field)

######################
# ACCRUAL ACCOUNTING #
######################

def sales_invoices_with_no_gl_entries_accrual_accounting(conditions, fields):
	""" to get the amounts of some Sales Invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabGL Entry`.", "")

	return """UNION ALL
			select {fields}
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabSales Invoice`.base_discount_amount = (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			and account_head = %(account_head)s
			{conditions}
			group by voucher_no
			""".format(conditions=conditions, fields=fields)

def purchase_invoices_with_no_gl_entries_accrual_accounting(conditions, fields):
	""" to get the amounts of some Purchase Invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabGL Entry`.", "")

	return """UNION ALL
			select {fields}
			from `tabPurchase Invoice`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabPurchase Invoice`.name
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			where `tabPurchase Invoice`.base_discount_amount = (tax_amount + `tabPurchase Invoice`.total)
			and `tabPurchase Invoice`.docstatus = 1
			and account_head = %(account_head)s
			{conditions}
			group by voucher_no
			""".format(conditions=conditions, fields=fields)

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

def get_cond_jv_roottype_not_equity():
	""" not show jv when root_type = Equity """
	return """and voucher_no not in (select `tabJournal Entry Account`.parent
			from `tabJournal Entry Account`
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.docstatus = 1
			and root_type = 'Equity')"""

def get_jv_fields_tax_collected_paid():
	""" to show correct positive/negative values of journal entries """
	# tax collected:
	# - if root_type = Income and debit > 0 then (debit*-1)
	# - if root_type = Income and debit = 0 then (debit)
	# - else 0.0
	# tax paid:
	# - if root_type = Expense and credit > 0 then (credit*-1)
	# - if root_type = Expense and credit = 0 then (credit)
	# - else 0.0"""
	return """case
		when (select root_type
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.parent = voucher_no
			and root_type in ('Expense', 'Income') group by root_type) = 'Income'
			and (select `tabJournal Entry Account`.debit_in_account_currency
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				where `tabJournal Entry Account`.parent = voucher_no
				and root_type in ('Expense', 'Income') group by root_type) > 0.0
			then `tabGL Entry`.debit_in_account_currency * -1.0
		when (select root_type
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.parent = voucher_no
			and root_type in ('Expense', 'Income') group by root_type) = 'Income'
			and (select `tabJournal Entry Account`.debit_in_account_currency
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				where `tabJournal Entry Account`.parent = voucher_no
				and root_type in ('Expense', 'Income') group by root_type) = 0.0
			then `tabGL Entry`.credit_in_account_currency
		else 0.0 end as tax_collected,
		case when (select root_type
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.parent = voucher_no
			and root_type in ('Expense', 'Income') group by root_type) = 'Expense'
			and (select `tabJournal Entry Account`.credit_in_account_currency
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				where `tabJournal Entry Account`.parent = voucher_no
				and root_type in ('Expense', 'Income') group by root_type) > 0.0
			then `tabGL Entry`.credit_in_account_currency * -1.0
		when (select root_type
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.parent = voucher_no
			and root_type in ('Expense', 'Income') group by root_type) = 'Expense'
			and (select `tabJournal Entry Account`.credit_in_account_currency
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				where `tabJournal Entry Account`.parent = voucher_no
				and root_type in ('Expense', 'Income') group by root_type) = 0.0
			then `tabGL Entry`.debit_in_account_currency
		else 0.0 end as tax_paid"""

def get_sinv_tax_total_accrual_accounting(filters, conditions, account_head):
	""" to get the sales invoice amounts of Accrual Accounting for some account """
	base_tax_sum_taxes_si = """(select sum(base_tax_amount_after_discount_amount)
		from `tabSales Taxes and Charges`, tabAccount
		where `tabSales Taxes and Charges`.account_head = tabAccount.name 
		and `tabSales Taxes and Charges`.parent = voucher_no
		and tabAccount.account_type = 'Tax') as base_tax_amount_after_discount_amount"""

	sales_fields = """concat(voucher_no, ': ', title) as voucher_no, base_tax_amount_after_discount_amount as tax_collected,
		0.0 as tax_paid, `tabGL Entry`.posting_date, account_name, total_taxes_and_charges, base_grand_total as grand_total,
		base_grand_total as sales_value, 0.0 as purchase_value,
		{base_tax_sum_taxes_si}""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

	si_with_no_gl_entries = """concat(`tabSales Invoice`.name, ': ', title) as voucher_no,
		base_tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid, posting_date, account_name,
		total_taxes_and_charges, base_grand_total as grand_total, base_grand_total as sales_value, 0.0 as purchase_value,
		{base_tax_sum_taxes_si}""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

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
			and root_type = 'Income'
			group by voucher_no
			{invoices_with_no_gl_entries}
			order by posting_date, voucher_no
			""".format(conditions=conditions,
					   sales_fields=sales_fields,
					   invoices_with_no_gl_entries=sales_invoices_with_no_gl_entries_accrual_accounting(
						   conditions, si_with_no_gl_entries)),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date,
				"account_head": account_head
			}, as_dict=True)

def get_pinv_tax_total_accrual_accounting(filters, conditions, account_head):
	""" to get the purchase invoices amounts of Accrual Accounting for some account """
	base_tax_amount_after_discount_amount = """if(add_deduct_tax = 'Deduct', base_tax_amount_after_discount_amount * -1,
		base_tax_amount_after_discount_amount)"""

	base_tax_sum_taxes_pi = """(select sum({base_tax_amount_after_discount_amount})
		from `tabPurchase Taxes and Charges`, tabAccount
		where `tabPurchase Taxes and Charges`.account_head = tabAccount.name 
		and `tabPurchase Taxes and Charges`.parent = voucher_no
		and tabAccount.account_type = 'Tax') as base_tax_amount_after_discount_amount""".format(
                                      base_tax_amount_after_discount_amount=base_tax_amount_after_discount_amount)

	purchase_fields = """concat(voucher_no, ': ', title) as voucher_no, 0.0 as tax_collected,
		sum({base_tax_amount_after_discount_amount}) as tax_paid, `tabGL Entry`.posting_date, account_name, total_taxes_and_charges,
		base_grand_total as grand_total, 0.0 as sales_value, base_grand_total as purchase_value, {base_tax_sum_taxes_pi}
		""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi,
	               base_tax_amount_after_discount_amount=base_tax_amount_after_discount_amount)

	pi_with_no_gl_entries = """concat(`tabPurchase Invoice`.name, ': ', title) as voucher_no,
		base_tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid, posting_date, account_name,
		total_taxes_and_charges, base_grand_total as grand_total, 0.0 as sales_value, base_grand_total as purchase_value,
		{base_tax_sum_taxes_pi}""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi)

	return frappe.db.sql("""
			select {purchase_fields}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			where account_head = %(account_head)s
			and `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabPurchase Invoice`.docstatus = 1
			{invoice_with_no_income_expense}
			{conditions}
			and tabAccount.account_name = 'Creditors'
			group by voucher_no
			{invoices_with_no_gl_entries}
			order by posting_date, voucher_no
			""".format(conditions=conditions,
	                   purchase_fields=purchase_fields,
	                   invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense("""`tabPurchase Invoice`.name"""),
	                   invoices_with_no_gl_entries=purchase_invoices_with_no_gl_entries_accrual_accounting(
		                   conditions, pi_with_no_gl_entries)),
					{
						"company": filters.company,
						"from_date": filters.from_date,
						"to_date": filters.to_date,
						"account_head": account_head
					}, as_dict=True)

def get_jv_tax_total_accrual(filters, conditions, account_head):
	""" to get the journal entries amounts of Accrual Accounting for some account """
	jv_fields = """concat(voucher_no, ': ', title) as voucher_no, {tax_collected_paid},	`tabJournal Entry`.posting_date,
		account_name, 0.0 as total_taxes_and_charges, 0.0 as grand_total, 0.0 as base_tax_amount_after_discount_amount,
		voucher_no as invoice, 0.0 as sales_value, 0.0 as purchase_value, '' as root_type
		""".format(tax_collected_paid=get_jv_fields_tax_collected_paid())

	join_and_cond = """from `tabGL Entry`
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
		left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
		where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
		and `tabGL Entry`.account = %(account_head)s
		and `tabJournal Entry`.docstatus = 1
		and (exists(select credit
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.parent = voucher_no
			and root_type in ('Expense', 'Income')))
		{jv_roottype_not_equity}
		{conditions}
		group by voucher_no""".format(conditions=conditions, jv_roottype_not_equity=get_cond_jv_roottype_not_equity())

	# to get tax collected and paid
	jv_map = frappe.db.sql("""select {jv_fields} 
		{join_and_cond}
		order by posting_date, voucher_no
		""".format(conditions=conditions,
	               jv_fields=jv_fields, join_and_cond=join_and_cond),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

	if jv_map:
		# to get purchase and sales values
		sales_purchase_values = frappe.db.sql("""select total_debit as sales_value, total_credit as purchase_value, '' as root_type,
			concat(`tabJournal Entry`.name, ': ', title) as voucher_no
			from `tabJournal Entry Account`
		    left join tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
		    left join `tabJournal Entry` ON `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		    where report_type = 'Profit and Loss'
		    and `tabJournal Entry Account`.parent in (
				select voucher_no
				{join_and_cond})
			group by voucher_no
			order by `tabJournal Entry`.posting_date, voucher_no
			""".format(conditions=conditions,
		               join_and_cond=join_and_cond),
					{
						"company": filters.company,
						"from_date": filters.from_date,
						"to_date": filters.to_date,
						"account_head": account_head
					}, as_dict=True)

		# to get root_type to check on prepare_data function
		root_type = frappe.db.sql("""select root_type, concat(voucher_no, ': ', title) as voucher_no
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			where voucher_no in (
				select voucher_no
				from `tabGL Entry`
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = `tabJournal Entry`.name
				where `tabGL Entry`.voucher_type in ('Journal Entry')
				and `tabJournal Entry`.docstatus = 1
				and `tabGL Entry`.account = %(account_head)s
				{conditions}
				and exists(select credit
					from `tabJournal Entry Account`
					left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type
					where `tabJournal Entry Account`.parent = voucher_no and root_type in ('Expense', 'Income'))
				{jv_roottype_not_equity}
				group by voucher_no)
			and root_type in ('Expense', 'Income')
			and `tabJournal Entry`.docstatus = 1
			group by voucher_no
			order by `tabGL Entry`.posting_date, voucher_no
			""".format(conditions=conditions, jv_roottype_not_equity=get_cond_jv_roottype_not_equity()),
                    {
	                    "company": filters.company,
	                    "from_date": filters.from_date,
	                    "to_date": filters.to_date,
	                    "account_head": account_head
                    }, as_dict=True)

		index = 0
		# update de values to return the data mapped
		for spv, rt in zip(sales_purchase_values, root_type):
			jv_map[index].sales_value = spv.get("sales_value")
			jv_map[index].purchase_value = spv.get("purchase_value")
			jv_map[index].root_type = rt.get("root_type")
			index += 1

	return jv_map

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
			{invoice_with_no_income_expense}
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
			and exists(select root_type
				 from `tabJournal Entry Account`
				 left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				 where `tabJournal Entry Account`.parent = voucher_no
				 and root_type in ('Expense', 'Income'))
			{jv_roottype_not_equity}
			{taxes}
			{conditions}
			group by node_rate, account_head
			{invoices_with_no_gl_entries}
			order by rate, account_head
			""".format(taxes=taxes, 
	                   conditions=conditions,
	                   jv_roottype_not_equity=get_cond_jv_roottype_not_equity(),
	                   invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense(
		                   """`tabPurchase Taxes and Charges`.parent"""),
	                   invoices_with_no_gl_entries=invoices_rates_with_no_gl_entries_accrual_accounting(conditions, taxes)),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)

###################
# CASH ACCOUNTING #
###################

def get_tax_total_cash_accounting(filters, conditions, account_head, conditions_payment_entry, conditions_date_gl, taxes):
	""" to get the sales/purchase amounts of Cash Accounting for some account """
	# UNION list (amounts):
	# Sales Invoices
	# Sales Invoices with new payment entry
	# Purchase Invoices
	# Purchase Invoices with new payment entry

	if account_head == "Invoices with no tax": # that invoices that don't have a tax account involved
		taxes_exceptions = taxes.replace("and tabAccount.name in", "")

		exceptions_sales_fields = """concat(`tabJournal Entry Account`.reference_name, ': ',
			`tabSales Invoice`.title) as voucher_no, 0.0 as tax_collected, 0.0 as tax_paid,
			`tabJournal Entry Account`.credit_in_account_currency sales_value, 0.0 as purchase_value,
			`tabGL Entry`.posting_date, account_name, `tabJournal Entry Account`.credit_in_account_currency total_taxes_and_charges,
	        `tabJournal Entry Account`.credit_in_account_currency as grand_total,
		    `tabJournal Entry Account`.credit_in_account_currency base_tax_amount_after_discount_amount"""

		exceptions_sales_fields_payment_entry = """concat(reference_name, ': ', `tabSales Invoice`.title) as voucher_no,
			0.0 as tax_collected, 0.0 as tax_paid, allocated_amount as sales_value, 0.0 as purchase_value,
			`tabGL Entry`.posting_date,	account_name, total_taxes_and_charges, base_grand_total as grand_total,
			base_grand_total as base_tax_amount_after_discount_amount"""

		exceptions_purchase_fields = """concat(`tabJournal Entry Account`.reference_name, ': ',
			`tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected, 0.0 as tax_paid,
			0.0 sales_value, `tabJournal Entry Account`.debit_in_account_currency as purchase_value,
			`tabGL Entry`.posting_date, account_name, `tabJournal Entry Account`.debit_in_account_currency total_taxes_and_charges,
	        `tabJournal Entry Account`.debit_in_account_currency as grand_total,
		    `tabJournal Entry Account`.debit_in_account_currency base_tax_amount_after_discount_amount"""

		exceptions_purchase_fields_payment_entry = """concat(reference_name, ': ', `tabPurchase Invoice`.title) as voucher_no,
			0.0 as tax_collected, 0.0 as tax_paid, 0.0 as sales_value, allocated_amount as purchase_value,
			`tabGL Entry`.posting_date,	account_name, total_taxes_and_charges, base_grand_total as grand_total,
			base_grand_total as base_tax_amount_after_discount_amount"""

		return frappe.db.sql("""select {exceptions_sales_fields}
			from `tabJournal Entry Account`
			left join `tabGL Entry` on `tabGL Entry`.voucher_no = `tabJournal Entry Account`.parent
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabJournal Entry Account`.reference_name
			where reference_name is not null
			and `tabJournal Entry Account`.reference_type in ('Sales Invoice')
			and reference_name not in (select distinct `tabSales Taxes and Charges`.parent
				from `tabSales Taxes and Charges`
				where `tabSales Taxes and Charges`.account_head in {taxes_exceptions}
			  	and `tabSales Taxes and Charges`.parenttype = 'Sales Invoice')
			{conditions_date_gl}
			group by `tabJournal Entry Account`.name
			UNION ALL
			select {exceptions_sales_fields_payment_entry}
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name= `tabGL Entry`.voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			left join `tabSales Invoice` on `tabSales Invoice`.name = reference_name
			where reference_doctype = 'Sales Invoice'
			and reference_name not in (select distinct `tabSales Taxes and Charges`.parent
	            from `tabSales Taxes and Charges`  where
	            `tabSales Taxes and Charges`.account_head in {taxes_exceptions}
	            and `tabSales Taxes and Charges`.parenttype = 'Sales Invoice')
			{conditions_date_gl}
			UNION ALL
			select {exceptions_purchase_fields}
			from `tabJournal Entry Account`
			left join `tabGL Entry` on `tabGL Entry`.voucher_no = `tabJournal Entry Account`.parent
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabJournal Entry Account`.reference_name
			where reference_name is not null
			and `tabJournal Entry Account`.reference_type in ('Purchase Invoice')
			and reference_name not in (select distinct `tabPurchase Taxes and Charges`.parent
				from `tabPurchase Taxes and Charges`
				where `tabPurchase Taxes and Charges`.account_head in {taxes_exceptions}
			  	and `tabPurchase Taxes and Charges`.parenttype = 'Purchase Invoice')
			{conditions_date_gl}
			group by `tabJournal Entry Account`.name
			UNION ALL
			select {exceptions_purchase_fields_payment_entry}
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name= `tabGL Entry`.voucher_no
			left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = reference_name
			where reference_doctype = 'Purchase Invoice'
			and reference_name not in (select distinct `tabPurchase Taxes and Charges`.parent
	            from `tabPurchase Taxes and Charges`  where
	            `tabPurchase Taxes and Charges`.account_head in {taxes_exceptions}
	            and `tabPurchase Taxes and Charges`.parenttype = 'Purchase Invoice')
			{conditions_date_gl}
			order by posting_date, voucher_no
			""".format(exceptions_sales_fields=exceptions_sales_fields,
		               exceptions_purchase_fields=exceptions_purchase_fields,
		               exceptions_sales_fields_payment_entry=exceptions_sales_fields_payment_entry,
		               exceptions_purchase_fields_payment_entry=exceptions_purchase_fields_payment_entry,
		               taxes_exceptions=taxes_exceptions,
		               conditions_date_gl=conditions_date_gl),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)
	else: # taxes involved
		base_tax_sum_taxes_pi = """(select sum(if(add_deduct_tax = 'Deduct', base_tax_amount_after_discount_amount *-1,
				base_tax_amount_after_discount_amount))
			from `tabPurchase Taxes and Charges`, tabAccount
			where `tabPurchase Taxes and Charges`.account_head = tabAccount.name 
			and `tabPurchase Taxes and Charges`.parent = voucher_no
			and tabAccount.account_type = 'Tax') as base_tax_amount_after_discount_amount"""

		base_tax_sum_taxes_si = """(select sum(base_tax_amount_after_discount_amount)
			from `tabSales Taxes and Charges`, tabAccount
			where `tabSales Taxes and Charges`.account_head = tabAccount.name
			and `tabSales Taxes and Charges`.parent = voucher_no
			and tabAccount.account_type = 'Tax') as base_tax_amount_after_discount_amount"""

		sales_fields = """concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no,
	       (`tabJournal Entry Account`.credit_in_account_currency / `tabSales Invoice`.base_grand_total)
	       * base_tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid,
	       `tabJournal Entry Account`.credit_in_account_currency as sales_value, 0.0 as purchase_value,
	       `tabJournal Entry`.posting_date, account_name, total_taxes_and_charges, base_grand_total as grand_total,
	       {base_tax_sum_taxes_si}""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

		sales_fields_new_payment = """concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no,
			(allocated_amount  / `tabSales Invoice`.base_grand_total) *	base_tax_amount_after_discount_amount as tax_collected,
			0.0 as tax_paid, allocated_amount as sales_value, 0.0 as purchase_value, `tabPayment Entry`.posting_date, account_name,
			total_taxes_and_charges, base_grand_total as grand_total, {base_tax_sum_taxes_si}
			""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

		purchase_fields = """concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected,
			if(add_deduct_tax = 'Deduct', (`tabJournal Entry Account`.debit_in_account_currency /
				`tabPurchase Invoice`.base_grand_total)	* base_tax_amount_after_discount_amount * -1,
			(`tabJournal Entry Account`.debit_in_account_currency / `tabPurchase Invoice`.base_grand_total)
				* base_tax_amount_after_discount_amount) as tax_paid, 0.0 as sales_value, (select sum(jea.debit_in_account_currency)
				from `tabJournal Entry Account` jea	where jea.reference_name = voucher_no
			and jea.parent = `tabJournal Entry Account`.parent) as purchase_value, `tabJournal Entry`.posting_date, account_name,
			total_taxes_and_charges, base_grand_total as grand_total, {base_tax_sum_taxes_pi}
			""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi)

		purchase_fields_new_payment = """concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected,
			if(add_deduct_tax = 'Deduct', (allocated_amount / `tabPurchase Invoice`.base_grand_total) *
				base_tax_amount_after_discount_amount * -1, (allocated_amount / `tabPurchase Invoice`.base_grand_total) *
				base_tax_amount_after_discount_amount) as tax_paid, 0.0 as sales_value, allocated_amount as purchase_value,
			`tabPayment Entry`.posting_date, account_name, total_taxes_and_charges, base_grand_total as grand_total,
			{base_tax_sum_taxes_pi}""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi)

		sales_just_payments = """and ( not exists (
	        select debit 
	        from `tabJournal Entry Account` 
	        where parent = voucher_no and ((account_type in ('Income Account', 'Chargeable', 'Expense Account')) 
	        and debit > 0.0) 
	        and ( select count(account_type) 
	        from `tabJournal Entry Account` 
	        where parent = voucher_no and (account_type = 'Receivable' and credit > 0.0))))"""

		purchase_just_payments = """and ( not exists ( select credit
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type 
			where `tabJournal Entry Account`.parent = voucher_no and root_type = 'Expense' and credit > 0.0 
			and ( select count(`tabJournal Entry Account`.account_type) 
			from `tabJournal Entry Account` 
			where parent = voucher_no and debit > 0.0) > 0))"""

		return frappe.db.sql("""
			select {sales_fields}
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where account_head = %(account_head)s
			and `tabJournal Entry Account`.parent in (select distinct voucher_no
				from `tabGL Entry`
				where voucher_type in ('Journal Entry', 'Payment Entry')
				and `tabGL Entry`.party_type = 'Customer'
				{sales_just_payments}
				{conditions})
			group by `tabJournal Entry Account`.parent, `tabSales Invoice`.name, `tabJournal Entry Account`.name
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
			and `tabPayment Entry`.docstatus = 1
			{conditions_payment_entry}
			and root_type = 'Income'
			group by reference_name, `tabPayment Entry`.name
			UNION ALL
			select {purchase_fields}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where account_head = %(account_head)s
			and `tabJournal Entry Account`.parent in (select distinct voucher_no
				from `tabGL Entry`
				where voucher_type in ('Journal Entry', 'Payment Entry')
				and `tabGL Entry`.party_type = 'Supplier'
				{purchase_just_payments}
				{conditions})
			{invoice_with_no_income_expense}
			group by `tabJournal Entry Account`.parent, `tabPurchase Invoice`.name, `tabPurchase Taxes and Charges`.name
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
			and `tabPayment Entry`.docstatus = 1
			{invoice_with_no_income_expense}
			{conditions_payment_entry}
			and tabAccount.account_name = 'Creditors'
			group by reference_name, `tabPayment Entry`.name
			order by posting_date, voucher_no
			""".format(conditions=conditions,
					   conditions_payment_entry=conditions_payment_entry,
					   sales_fields=sales_fields,
					   sales_fields_new_payment=sales_fields_new_payment,
					   sales_just_payments=sales_just_payments,
					   purchase_fields=purchase_fields,
					   purchase_fields_new_payment=purchase_fields_new_payment,
					   purchase_just_payments=purchase_just_payments,
					   taxes=taxes,
					   invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense("""`tabPurchase Invoice`.name""")),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

def get_rates_cash_accounting(filters, conditions, conditions_payment_entry, conditions_date_gl, taxes):
	""" to get the rates (nodes) of Cash Accounting """
	# UNION list (rates/nodes):
	# Sales Invoices
	# Sales Invoices with new payment entry
	# Purchase Invoices
	# Purchase Invoices with new payment entry

	return frappe.db.sql("""
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name 
			from `tabSales Taxes and Charges`
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
				where `tabSales Taxes and Charges`.parent in (
				select distinct voucher_no
				from `tabGL Entry`
				left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
				left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				where `tabJournal Entry Account`.parent in (select distinct voucher_no
					from `tabGL Entry`
					where voucher_type in ('Journal Entry', 'Payment Entry')
					and `tabGL Entry`.party_type = 'Customer'
					and ( not exists (
			            select debit 
			            from `tabJournal Entry Account` 
			            where parent = voucher_no and ((account_type in ('Income Account', 'Chargeable', 'Expense Account')) 
			            and debit > 0.0) 
			            and ( select count(account_type) 
			            from `tabJournal Entry Account` 
			            where parent = voucher_no and (account_type = 'Receivable' and credit > 0.0))))
					{conditions_date_gl}))
			{taxes}
			group by node_rate, account_name
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name 
			from `tabSales Taxes and Charges`
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabSales Taxes and Charges`.parent in (select distinct  voucher_no
				from `tabGL Entry`
				left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
				left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
				left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
				where `tabGL Entry`.voucher_type in ('Sales Invoice')
				and `tabPayment Entry`.docstatus = 1
				{conditions_payment_entry}
				and root_type = 'Income')
			{taxes}
			group by node_rate, account_name
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name 
			from `tabPurchase Taxes and Charges`
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			where `tabPurchase Taxes and Charges`.parent in (select distinct voucher_no
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where `tabJournal Entry Account`.parent in (select distinct voucher_no
				from `tabGL Entry`
				where voucher_type in ('Journal Entry', 'Payment Entry')
				and `tabGL Entry`.party_type = 'Supplier'
				and ( not exists ( select credit
					from `tabJournal Entry Account`
					left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type 
					where `tabJournal Entry Account`.parent = voucher_no and root_type = 'Expense' and credit > 0.0 
					and ( select count(`tabJournal Entry Account`.account_type) 
					from `tabJournal Entry Account` 
					where parent = voucher_no and debit > 0.0) > 0))
				{conditions})
			{invoice_with_no_income_expense})
			{taxes}
			group by node_rate, account_name
			UNION
			select round(tax_rate, 2) as rate, concat(round(tax_rate, 2), '%% - ', tabAccount.name) as node_rate,
				tabAccount.name as account_head, account_name 
			from `tabPurchase Taxes and Charges`
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			where `tabPurchase Taxes and Charges`.parent in (select distinct voucher_no
				from `tabGL Entry`
				left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
				left join tabAccount on tabAccount.name = `tabGL Entry`.account
				left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
				left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
				left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
				where `tabGL Entry`.voucher_type in ('Purchase Invoice')
				and `tabPayment Entry`.docstatus = 1
				{invoice_with_no_income_expense}
				{conditions_payment_entry}
				and tabAccount.account_name = 'Creditors')
			{taxes}
			group by node_rate, account_name
			{get_node_rate_no_tax_cash_accounting}
			order by rate, account_head
			""".format(taxes=taxes,
					   conditions=conditions,
					   conditions_payment_entry=conditions_payment_entry,
					   conditions_date_gl=conditions_date_gl,
					   invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense(
						   """`tabPurchase Taxes and Charges`.parent"""),
					   get_node_rate_no_tax_cash_accounting=get_node_rate_no_tax_cash_accounting(taxes,conditions_date_gl)),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)

def get_node_rate_no_tax_cash_accounting(taxes, conditions_date_gl):
	""" to get the rates (nodes) for those invoices that have no taxes of Cash Accounting """
	taxes = taxes.replace("and tabAccount.name in", "")
	field = "'Invoices with no tax'"

	exceptions_jv_sales = """UNION select distinct {field} as rate, {field} as node_rate, {field} as account_head,
		{field} as account_name
		from `tabJournal Entry Account`
		left join `tabGL Entry` on `tabGL Entry`.voucher_no = `tabJournal Entry Account`.parent
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		where reference_name is not null
		and `tabJournal Entry Account`.reference_type in ('Purchase Invoice')
		and reference_name not in (select distinct `tabPurchase Taxes and Charges`.parent
            from `tabPurchase Taxes and Charges`  where
            `tabPurchase Taxes and Charges`.account_head IN {taxes}
            and `tabPurchase Taxes and Charges`.parenttype = 'Purchase Invoice')
		{conditions_date_gl}""".format(taxes=taxes, conditions_date_gl=conditions_date_gl, field=field)

	exceptions_jv_Purchase = """UNION select distinct {field} as rate, {field} as node_rate, {field} as account_head,
		{field} as account_name
		from `tabJournal Entry Account`
		left join `tabGL Entry` on `tabGL Entry`.voucher_no = `tabJournal Entry Account`.parent
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		where reference_name is not null
		and `tabJournal Entry Account`.reference_type in ('Sales Invoice')
		and reference_name not in (select distinct `tabSales Taxes and Charges`.parent
            from `tabSales Taxes and Charges`  where
            `tabSales Taxes and Charges`.account_head IN {taxes}
            and `tabSales Taxes and Charges`.parenttype = 'Sales Invoice')
		{conditions_date_gl}""".format(taxes=taxes, conditions_date_gl=conditions_date_gl, field=field)

	exceptions_pe_Sales = """UNION select distinct {field} as rate, {field} as node_rate, {field} as account_head,
		{field} as account_name
		from `tabGL Entry`
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name= `tabGL Entry`.voucher_no
		left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
		where reference_doctype = 'Sales Invoice'
		and reference_name not in (select distinct `tabSales Taxes and Charges`.parent
            from `tabSales Taxes and Charges`  where
            `tabSales Taxes and Charges`.account_head IN {taxes}
	        and `tabSales Taxes and Charges`.parenttype = 'Sales Invoice')
	    {conditions_date_gl}""".format(taxes=taxes, conditions_date_gl=conditions_date_gl, field=field)

	exceptions_pe_Purchase = """UNION select distinct {field} as rate, {field} as node_rate, {field} as account_head,
		{field} as account_name
		from `tabGL Entry`
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name= `tabGL Entry`.voucher_no
		left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
		where reference_doctype = 'Purchase Invoice'
		and reference_name not in (select distinct `tabPurchase Taxes and Charges`.parent
            from `tabPurchase Taxes and Charges`  where
            `tabPurchase Taxes and Charges`.account_head IN {taxes}
	        and `tabPurchase Taxes and Charges`.parenttype = 'Purchase Invoice')
	    {conditions_date_gl}""".format(taxes=taxes, conditions_date_gl=conditions_date_gl, field=field)

	return exceptions_jv_sales + exceptions_jv_Purchase + exceptions_pe_Sales + exceptions_pe_Purchase

def get_jv_tax_total_cash(filters, conditions, account_head):
	""" to get the journal vouchers amounts of Cash Accounting for some account """

	jv_fields = """concat(voucher_no, ': ', title) as voucher_no, {tax_collected_paid},	`tabJournal Entry`.posting_date,
		account_name, 0.0 as total_taxes_and_charges, 0.0 as grand_total, 0.0 as base_tax_amount_after_discount_amount,
		voucher_no as invoice, 0.0 as sales_value, 0.0 as purchase_value, '' as root_type
		""".format(tax_collected_paid=get_jv_fields_tax_collected_paid())

	join_and_cond = """from `tabGL Entry`
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
		left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
		where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
		and `tabGL Entry`.account = %(account_head)s
		and `tabJournal Entry`.docstatus = 1
		and `tabJournal Entry Account`.parent in (select `tabJournal Entry Account`.parent
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			where `tabJournal Entry Account`.docstatus = 1
			{conditions}
			and tabAccount.account_type in ('Bank', 'Cash'))
		{jv_roottype_not_equity}
		{conditions}
		group by voucher_no""".format(conditions=conditions, jv_roottype_not_equity=get_cond_jv_roottype_not_equity())

	jv_map = frappe.db.sql("""select {jv_fields}
	        {join_and_cond}
			order by posting_date, voucher_no
			""".format(conditions=conditions, jv_fields=jv_fields, join_and_cond=join_and_cond),
			{
			   "company": filters.company,
			   "from_date": filters.from_date,
			   "to_date": filters.to_date,
			   "account_head": account_head
			}, as_dict=True)

	if jv_map:
		sales_purchase_values = frappe.db.sql("""select total_debit as sales_value, total_credit as purchase_value, '' as root_type,
			concat(`tabJournal Entry`.name, ': ', title) as voucher_no
			from `tabJournal Entry Account`
		    left join tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
		    left join `tabJournal Entry` ON `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		    where report_type = 'Profit and Loss'
		    and `tabJournal Entry Account`.parent in (
		    	select voucher_no
				{join_and_cond})
			group by voucher_no
			order by `tabJournal Entry`.posting_date, voucher_no""".format(join_and_cond=join_and_cond),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

		root_type = frappe.db.sql("""select root_type, concat(voucher_no, ': ', title) as voucher_no
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			where voucher_no in (
				select voucher_no
				{join_and_cond})
			and root_type in ('Expense', 'Income')
			and `tabJournal Entry`.docstatus = 1
			group by voucher_no
			order by `tabGL Entry`.posting_date, voucher_no""".format(join_and_cond=join_and_cond),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date,
					"account_head": account_head
				}, as_dict=True)

		index = 0
		for spv, rt in zip(sales_purchase_values, root_type):
			jv_map[index].sales_value = spv.get("sales_value")
			jv_map[index].purchase_value = spv.get("purchase_value")
			jv_map[index].root_type = rt.get("root_type")
			index += 1

	return jv_map