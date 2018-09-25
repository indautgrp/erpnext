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
	taxes, nodes = get_coa_taxes()

	if taxes == "":
		frappe.msgprint(_("No account is set to show in tax report"))
		return [], []

	# fix $ symbol when switching between dt/reports
	company_currency = frappe.db.get_value("Company", filters.company, "default_currency")

	if filters.accounting == "Accrual Accounting":
		data = get_data_accrual_accounting(filters, taxes, nodes, company_currency)
	else: # Cash Accounting
		data = get_data_cash_accounting(filters, taxes, nodes, company_currency)

	return columns, data

def validate_date_range(filters):
	dates = filters.date_range.split(" ")
	if dates:
		filters.from_date = datetime.strptime(dates[0], '%d-%m-%Y').strftime('%Y-%m-%d')
		filters.to_date = datetime.strptime(dates[2], '%d-%m-%Y').strftime('%Y-%m-%d')
		del filters["date_range"]

def get_data_accrual_accounting(filters, taxes, nodes, company_currency):
	conditions = get_conditions_accrual_accounting(filters)
	data = prepare_data(nodes, filters, conditions, taxes, company_currency)
	data = prepare_taxed_docs_node_one(data, company_currency)
	data = prepare_excluded_docs_node_one(data, company_currency, filters, conditions)

	return data

def get_data_cash_accounting(filters, taxes, nodes, company_currency):
	row_exception_node = frappe._dict({
		'name': "Invoices with no tax",
		"rate": None,
		"account_name": "Invoices with no tax",
		"account_head": "Invoices with no tax",
		"node_rate": "Invoices with no tax"
	})
	nodes.append(row_exception_node)

	conditions, conditions_payment_entry, conditions_date_gl = get_conditions_cash_accounting(filters)
	data = prepare_data(nodes, filters, conditions, taxes, company_currency, conditions_payment_entry, conditions_date_gl)
	data = prepare_taxed_docs_node_one(data, company_currency)
	data = prepare_excluded_docs_node_one(data, company_currency, filters, conditions, conditions_payment_entry, conditions_date_gl)

	return data

def get_coa_taxes_not_gst():
	""" From Chart of Accounts - Should the checkbox show_in_tax_reports not ticked """

	account_head = ""

	coa_taxes = frappe.db.sql("""select name as account_head from tabAccount where show_in_tax_reports = 0 order by account_name
		""", as_dict=True)

	for ct in coa_taxes:
		account = ct["account_head"]
		account_head = account_head + "'" + account.replace("'", "''") + "'" + ","

	if len(account_head) > 0:
		account_head = account_head[:-2] # remove last comma and single quote
		account_head = account_head[1:]  # remove first single quote

	return account_head

def get_coa_taxes():
	""" From Chart of Accounts - Should be a tax and the checkbox show_in_tax_reports must be checked """
	coa_taxes = ""

	nodes = frappe.db.sql("""select name, round(tax_rate, 2) as rate, account_name, name as account_head,
			concat(round(tax_rate, 2), '% - ', account_name) as node_rate
		from tabAccount
		where show_in_tax_reports = 1
		order by node_rate, account_name""", as_dict=True)

	for ct in nodes:
		coa_taxes += "'" + ct.name + "',"

	if coa_taxes != "":
		coa_taxes = "and tabAccount.name in (" + coa_taxes[:len(coa_taxes)-1] + ") "

	return coa_taxes, nodes

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

###################################################################################################################################
# CONDITIONS - EXCEPTIONS #
###################################################################################################################################

def get_cond_invoice_with_no_income_expense(field):
	""" to get invoices with no income or expense account """
	return """and exists (select voucher_no from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			where voucher_no = {field}
			and (root_type in ('Expense', 'Income') or tabAccount.account_type = 'Stock Received But Not Billed'))
			""".format(field=field)

def get_cond_jv_roottype_not_equity():
	""" not show jv when root_type = Equity """
	return """and voucher_no not in (select `tabJournal Entry Account`.parent
			from `tabJournal Entry Account`
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.docstatus = 1
			and root_type = 'Equity')"""

###################################################################################################################################
# PREPARE DATA #
###################################################################################################################################

def prepare_data(nodes, filters, conditions, taxes, company_currency, conditions_payment_entry="", conditions_date_gl=""):
	""" to prepare the data fields to be shown in the grid """
	data = []
	grand_total_sale = 0.0
	grand_total_purchase = 0.0
	total_tax_collected = 0.0
	total_tax_paid = 0.0
	has_data = False

	# to create a list of invoices and to show invoice's values splitted when have more than 1 entry showing in the grid
	split_invoices = []
	multi_invoice = {}

	# to sum base_tax_amount_after_discount_amount
	base_tax_sum_taxes_si = get_base_tax_sum_taxes_si()
	# to sum base_tax_amount_after_discount_amount and checks add_deduct field
	base_tax_sum_taxes_pi = get_base_tax_sum_taxes_pi()
	# to not show jv when root_type = Equity
	cond_jv_roottype_not_equity = get_cond_jv_roottype_not_equity()

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
			"currency": company_currency,
			"part_total_payment": None
		}

		if filters.accounting == "Accrual Accounting":
			value_added_tax = sorted(get_value_added_tax_accrual_accounting(filters, conditions, n.account_head,
                base_tax_sum_taxes_si, base_tax_sum_taxes_pi, cond_jv_roottype_not_equity),
                     key=lambda k: k['posting_date'])
		else: # Cash Accounting
			value_added_tax = sorted(
				get_value_added_tax_cash_accounting(filters, conditions, n.account_head, conditions_payment_entry,
                    conditions_date_gl, taxes, base_tax_sum_taxes_si, base_tax_sum_taxes_pi, cond_jv_roottype_not_equity),
						key=lambda k: k['posting_date'])

		if len(value_added_tax) > 0:
			data.append(row_node)

			# to update totals in each node line
			position_node = len(data)
			indent = 2

			# get a list of all rows in the grid
			for c in value_added_tax:
				split_invoices.append(c.voucher_no)

			for d in value_added_tax:
				# root_type for jv and to show correct values
				if "JV-" in d.voucher_no:
					# to show correct positive/negative values of journal vouchers
					# tax collected:
					# - if root_type = Income and debit > 0 then (debit*-1)
					# - if root_type = Income and debit = 0 then (credit)
					# - else 0.0
					# tax paid:
					# - if root_type = Expense and credit > 0 then (credit*-1)
					# - if root_type = Expense and credit = 0 then (debit)
					# - else 0.0"""
					if d.root_type == "Expense":
						if d.credit_in_account_currency > 0.0:
							d.tax_paid = d.credit_in_account_currency * -1
							d.purchase_value *= -1
						elif d.credit_in_account_currency == 0.0:
							d.tax_paid = d.debit_in_account_currency
						else:
							d.tax_paid = 0.0
						d.sales_value = 0.0
						d.tax_collected = 0.0
					else:
						if d.debit_in_account_currency > 0.0:
							d.tax_collected = d.debit_in_account_currency * -1
							d.sales_value *= -1
						elif d.debit_in_account_currency == 0.0:
							d.tax_collected = d.credit_in_account_currency
						else:
							d.tax_collected = 0.0
						d.purchase_value = 0.0
						d.tax_paid = 0.0

				ptp = 0 # part_total_payment Accrual
				if filters.accounting == "Cash Accounting":
					ptp = d.part_total_payment # 1 if is part payment

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
					"currency": company_currency,
					"part_total_payment": ptp
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
				"currency": company_currency,
				"part_total_payment": n.part_total_payment
			}

			# grand total line
			total_tax_collected += tax_collected_node
			total_tax_paid += tax_paid_node
			grand_total_sale += grand_total_sale_node
			grand_total_purchase += grand_total_purchase_node

			has_data = True

	if has_data:
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
			"currency": company_currency,
			"part_total_payment": None
		}

		data.append(row_total)

		# to count how many times each invoice is shown
		for i in split_invoices:
			if i in multi_invoice:
				multi_invoice[i] += 1
			else:
				multi_invoice[i] = 1

		# update sales/purchase value with value splitted
		have_multi_invoices = False
		for d in data:
			for m in multi_invoice:
				if d["rate"] == m and multi_invoice[m] > 1:
					have_multi_invoices = True
					if d["total_taxes_and_charges"] == 0.0:
						if d["tax_paid"] != 0.0 and d["base_tax_amount_after_discount_amount"] != 0.0:
							d["purchase_value"] = 0.0
							d["sales_value"] = 0.0
						else:
							d["purchase_value"] = d["purchase_value"]
					else:
						if d["base_tax_amount_after_discount_amount"] != 0.0:
							if d["purchase_value"] == d["grand_total"]:
								d["purchase_value"] = d["purchase_value"] * (d["tax_paid"] / d["base_tax_amount_after_discount_amount"])
								d["sales_value"] = d["sales_value"] * (d["tax_collected"] / d["base_tax_amount_after_discount_amount"])
							else:
								d["purchase_value"] = d["grand_total"] * (d["tax_paid"] / d["base_tax_amount_after_discount_amount"])
								d["sales_value"] = d["grand_total"] * (d["tax_collected"] / d["base_tax_amount_after_discount_amount"])
					data[data.count(d) - 1]["purchase_value"] = d["purchase_value"]
					data[data.count(d) - 1]["sales_value"] = d["sales_value"]

		if have_multi_invoices:
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

	if filters.accounting == "Cash Accounting":
		for d in data:
			if d["part_total_payment"] == 1:
				d["rate"] = "[ / ] " + d["rate"]

	return data

def prepare_taxed_docs_node_one(data, company_currency):
	data_taxed_docs = []
	taxed_docs = "Taxed Documents"

	row_node = {
		"date": None,
		"account_name": taxed_docs,
		"total_taxes_and_charges": None,
		"rate": taxed_docs,
		"sales_value": None,
		"purchase_value": None,
		"tax_collected": None,
		"tax_paid": None,
		"parent_labels": None,
		"indent": 0,
		"currency": company_currency
	}
	data_taxed_docs.append(row_node)

	for d in data:
		if d["indent"] == 1:
			row = {
				"date": d["date"],
				"account_name": d["account_name"],
				"total_taxes_and_charges": d["total_taxes_and_charges"],
				"rate": d["rate"],
				"sales_value": d["sales_value"],
				"purchase_value": d["purchase_value"],
				"tax_collected": d["tax_collected"],
				"tax_paid": d["tax_paid"],
				"parent_labels": taxed_docs,
				"indent": 1,
				"currency": d["currency"]
			}
		else:
			row = {
				"date": d["date"],
				"account_name": d["account_name"],
				"total_taxes_and_charges": d["total_taxes_and_charges"],
				"rate": d["rate"],
				"sales_value": d["sales_value"],
				"purchase_value": d["purchase_value"],
				"tax_collected": d["tax_collected"],
				"tax_paid": d["tax_paid"],
				"grand_total": d["grand_total"],
				"base_tax_amount_after_discount_amount": d["base_tax_amount_after_discount_amount"],
				"parent_labels": d["parent_labels"],
				"indent": 2,
				"currency": d["currency"]
			}

		data_taxed_docs.append(row)

	data_taxed_docs[0]["sales_value"] = data_taxed_docs[len(data_taxed_docs) - 1]["sales_value"]         # grand_total_sale
	data_taxed_docs[0]["purchase_value"] = data_taxed_docs[len(data_taxed_docs) - 1]["purchase_value"]   # grand_total_purchase
	data_taxed_docs[0]["tax_collected"] = data_taxed_docs[len(data_taxed_docs) - 1]["tax_collected"]     # total_tax_collected
	data_taxed_docs[0]["tax_paid"] = data_taxed_docs[len(data_taxed_docs) - 1]["tax_paid"]               # total_tax_paid

	data_taxed_docs = data_taxed_docs[:-1]  # remove total line 

	return data_taxed_docs

def prepare_excluded_docs_node_one(data, company_currency, filters, conditions, conditions_payment_entry="", conditions_date_gl=""):
	taxed_docs = "Excluded"

	row_node = {
		"date": None,
		"account_name": taxed_docs,
		"total_taxes_and_charges": None,
		"rate": taxed_docs,
		"sales_value": None,
		"purchase_value": None,
		"tax_collected": None,
		"tax_paid": None,
		"parent_labels": None,
		"indent": 0,
		"currency": company_currency
	}

	where_excluded_jv = """and `tabJournal Entry`.name not in (select parent from `tabJournal Entry Account` where account in (
		select name from tabAccount where show_in_tax_reports = 1 order by account_name))"""

	where_excluded_si = """and `tabSales Invoice`.name not in (select parent from `tabSales Taxes and Charges` where account_head
		in (select name from tabAccount where show_in_tax_reports = 1 order by account_name))"""

	where_excluded_pi = """and `tabPurchase Invoice`.name not in (select parent from `tabPurchase Taxes and Charges` where
		account_head in (select name from tabAccount where show_in_tax_reports = 1 order by account_name))"""

	if filters.accounting == "Accrual Accounting":
		value_added_tax = sorted((
			get_sinv_tax_total_accrual_accounting(filters, conditions, get_coa_taxes_not_gst(), get_base_tax_sum_taxes_si(), where_excluded_si)
			+ get_sinv_tax_total_invoices_with_no_gl_entries_accrual_accounting(filters, conditions, get_coa_taxes_not_gst(), get_base_tax_sum_taxes_si(), where_excluded_si)
			+ get_pinv_tax_total_accrual_accounting(filters, conditions, get_coa_taxes_not_gst(), get_base_tax_sum_taxes_pi(), where_excluded_pi)
			+ get_pinv_tax_total_invoices_with_no_gl_entries_accrual_accounting(filters, conditions, get_coa_taxes_not_gst(), get_base_tax_sum_taxes_pi(), where_excluded_pi)
			+ get_jv_tax_total_accrual(filters, conditions, get_coa_taxes_not_gst(), get_cond_jv_roottype_not_equity(), where_excluded_jv)
		), key=lambda k: k['posting_date'])
	else:  # Cash Accounting
		value_added_tax = sorted((
			get_si_tax_total_cash_accounting(filters, conditions, get_coa_taxes_not_gst(), get_base_tax_sum_taxes_si(), where_excluded_si)
			+ get_si_new_payment_tax_total_cash_accounting(filters, get_coa_taxes_not_gst(), conditions_payment_entry, get_base_tax_sum_taxes_si(), where_excluded_si)
			+ get_pi_tax_total_cash_accounting(filters, conditions, get_coa_taxes_not_gst(), get_base_tax_sum_taxes_pi(), where_excluded_pi)
			+ get_pi_new_payment_tax_total_cash_accounting(filters, get_coa_taxes_not_gst(), conditions_payment_entry, get_base_tax_sum_taxes_pi(), where_excluded_pi)
			+ get_jv_tax_total_accrual(filters, conditions, get_coa_taxes_not_gst(), get_cond_jv_roottype_not_equity(), where_excluded_jv)
		), key=lambda k: k['posting_date'])

	if len(value_added_tax) > 0:
		data.append(row_node)

		# to update totals in each node line
		position_node = len(data)
		indent = 1

		grand_total_sale_node = 0.0
		grand_total_purchase_node = 0.0

		for d in value_added_tax:
			# root_type for jv and to show correct values
			if "JV-" in d.voucher_no:
				if d.root_type == "Expense":
					if d.credit_in_account_currency > 0.0:
						d.tax_paid = 0.0
					elif d.credit_in_account_currency == 0.0:
						d.tax_paid = 0.0
					else:
						d.tax_paid = 0.0
					d.sv = 0.0
					d.tax_collected = 0.0
				else:
					if d.debit_in_account_currency > 0.0:
						d.tax_collected = 0.0
					elif d.debit_in_account_currency == 0.0:
						d.tax_collected = 0.0
					else:
						d.tax_collected = 0.0
					d.pv = 0.0
					d.tax_paid = 0.0

			row = {
				"date": d.posting_date,
				"account_name": d.account_name,
				"total_taxes_and_charges": d.total_taxes_and_charges,
				"rate": d.voucher_no,
				"sales_value": d.sv,
				"purchase_value": d.pv,
				"tax_collected": d.tax_collected,
				"tax_paid": d.tax_paid,
				"grand_total": d.grand_total,
				"base_tax_amount_after_discount_amount": d.base_tax_amount_after_discount_amount,
				"parent_labels": "Excluded",
				"indent": indent,
				"currency": company_currency
			}

			data.append(row)

			grand_total_sale_node += d.sv
			grand_total_purchase_node += d.pv

		# update total 
		data[position_node - 1] = {
			"date": None,
			"account_name": data[position_node - 1]["account_name"],
			"total_taxes_and_charges": data[position_node - 1]["total_taxes_and_charges"],
			"tax_collected": 0.0,
			"tax_paid": 0.0,
			"sales_value": grand_total_sale_node,
			"purchase_value": grand_total_purchase_node,
			"parent_labels": None,
			"rate": data[position_node - 1]["rate"],
			"indent": indent - 1,
			"currency": company_currency
		}

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

def get_base_tax_sum_taxes_si():
	""" to sum base_tax_amount_after_discount_amount of sales invoices """
	return """(select sum(base_tax_amount_after_discount_amount)
		from `tabSales Taxes and Charges`, tabAccount
		where `tabSales Taxes and Charges`.account_head = tabAccount.name
		and `tabSales Taxes and Charges`.parent = voucher_no
		and tabAccount.account_type = 'Tax') as base_tax_amount_after_discount_amount"""

def get_base_tax_sum_taxes_pi():
	""" to sum base_tax_amount_after_discount_amount (adding or deducting) of purchase invoices """
	return """(select sum(if(add_deduct_tax = 'Deduct', base_tax_amount_after_discount_amount *-1,
			base_tax_amount_after_discount_amount))
		from `tabPurchase Taxes and Charges`, tabAccount
		where `tabPurchase Taxes and Charges`.account_head = tabAccount.name
		and `tabPurchase Taxes and Charges`.parent = voucher_no
		and tabAccount.account_type = 'Tax') as base_tax_amount_after_discount_amount"""

###################################################################################################################################
# ACCRUAL ACCOUNTING #
###################################################################################################################################

def get_value_added_tax_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_si, base_tax_sum_taxes_pi, cond_jv_roottype_not_equity):
	""" to get sales/purchase invoices and return to prepare_data function """
	return (get_sinv_tax_total_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_si) +
       get_sinv_tax_total_invoices_with_no_gl_entries_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_si) +
       get_pinv_tax_total_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_pi) +
       get_pinv_tax_total_invoices_with_no_gl_entries_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_pi) +
       get_jv_tax_total_accrual(filters, conditions, account_head, cond_jv_roottype_not_equity))

def get_sinv_tax_total_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_si, excluded=""):
	""" to get the sales invoice amounts of Accrual Accounting """
	sales_fields = """concat(voucher_no, ': ', title) as voucher_no, base_tax_amount_after_discount_amount as tax_collected,
		0.0 as tax_paid, `tabGL Entry`.posting_date, account_name, total_taxes_and_charges, base_grand_total as grand_total,
		base_grand_total as sales_value, 0.0 as purchase_value, base_grand_total as sv, 0.0 as pv,
		{base_tax_sum_taxes_si}""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

	return frappe.db.sql("""
			select {sales_fields}
			from `tabGL Entry`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
			where account_head in ('{account_head}')
			and `tabGL Entry`.voucher_type in ('Sales Invoice')
			and `tabSales Invoice`.docstatus = 1
			{conditions}
			{excluded}
			and root_type = 'Income'
			group by voucher_no
			order by posting_date, voucher_no
			""".format(conditions=conditions, sales_fields=sales_fields, account_head=account_head, excluded=excluded),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

def get_pinv_tax_total_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_pi, excluded=""):
	""" to get the purchase invoices amounts of Accrual Accounting """
	purchase_fields = """concat(voucher_no, ': ', title) as voucher_no, 0.0 as tax_collected,
		sum(if(add_deduct_tax = 'Deduct', base_tax_amount_after_discount_amount * -1,
		base_tax_amount_after_discount_amount)) as tax_paid, `tabGL Entry`.posting_date, account_name, total_taxes_and_charges,
		base_grand_total as grand_total, 0.0 as sales_value, base_grand_total as purchase_value, 0.0 as sv, base_grand_total as pv,
		{base_tax_sum_taxes_pi}
		""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi)

	return frappe.db.sql("""
			select {purchase_fields}
			from `tabGL Entry`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
			where account_head in ('{account_head}')
			and `tabGL Entry`.voucher_type in ('Purchase Invoice')
			and `tabPurchase Invoice`.docstatus = 1
			{invoice_with_no_income_expense}
			{conditions}
			{excluded}
			and tabAccount.account_name = 'Creditors'
			group by voucher_no
			order by posting_date, voucher_no
			""".format(conditions=conditions,
	                   purchase_fields=purchase_fields,
	                   invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense("""`tabPurchase Invoice`.name"""),
	                   account_head=account_head, excluded=excluded),
					{
						"company": filters.company,
						"from_date": filters.from_date,
						"to_date": filters.to_date
					}, as_dict=True)

def get_jv_tax_total_accrual(filters, conditions, account_head, cond_jv_roottype_not_equity, excluded=""):
	""" to get the journal vouchers amounts of Accrual Accounting """
	jv_fields = """voucher_no as journal_voucher, concat(voucher_no, ': ', title) as voucher_no,
		`tabJournal Entry`.posting_date, account_name, 0.0 as total_taxes_and_charges, 0.0 as grand_total,
		0.0 as base_tax_amount_after_discount_amount, voucher_no as invoice, 0.0 as sales_value, 0.0 as purchase_value,
		`tabJournal Entry`.total_debit as sv, `tabJournal Entry`.total_credit as pv """

	# to get tax collected and paid
	jv_map = frappe.db.sql("""select {jv_fields} 
		from `tabGL Entry`
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
		left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
		where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
		and `tabGL Entry`.account in ('{account_head}')
		and `tabJournal Entry`.docstatus = 1
		and (exists(select credit
			from `tabJournal Entry Account`
			left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
			where `tabJournal Entry Account`.parent = voucher_no
			and root_type in ('Expense', 'Income')))
		{jv_roottype_not_equity}
		{conditions}
		{excluded}
		group by voucher_no
		order by posting_date, voucher_no
		""".format(conditions=conditions, jv_fields=jv_fields, jv_roottype_not_equity=cond_jv_roottype_not_equity,
	               account_head=account_head, excluded=excluded),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)

	invoices = ""
	for invoice in jv_map:
		invoices += "'" + invoice.journal_voucher + "',"

	if invoices != "":
		invoices = invoices[:len(invoices)-1]

	if jv_map:
		# to get purchase and sales values
		sales_purchase_values = frappe.db.sql("""select total_debit as sales_value, if(SUM(debit_in_account_currency) = 0,
			SUM(credit_in_account_currency), SUM(debit_in_account_currency)) as purchase_value, root_type,
			concat(`tabJournal Entry`.name, ': ', title) as voucher_no
			from `tabJournal Entry Account`
		    left join tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
		    left join `tabJournal Entry` ON `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		    where report_type = 'Profit and Loss'
		    and `tabJournal Entry Account`.parent in ({invoices})
			group by voucher_no
			order by `tabJournal Entry`.posting_date, voucher_no
			""".format(invoices=invoices),
					{
						"company": filters.company,
						"from_date": filters.from_date,
						"to_date": filters.to_date
					}, as_dict=True)

		# to get debit and credit to use as tax paid/collected
		tax_collected_paid = frappe.db.sql("""
			select voucher_no, `tabGL Entry`.debit_in_account_currency, `tabGL Entry`.credit_in_account_currency
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
			where `tabJournal Entry Account`.parent in ({invoices})
			and `tabGL Entry`.account in ('{account_head}')
			group by voucher_no
			order by `tabJournal Entry`.posting_date, voucher_no
			""".format(invoices=invoices, account_head=account_head), as_dict=True)

		index = 0
		# update de values to return the data mapped
		for spv, tcp in zip(sales_purchase_values, tax_collected_paid):
			jv_map[index].sales_value = spv.get("sales_value")
			jv_map[index].purchase_value = \
				spv.get("purchase_value") + tcp.get("debit_in_account_currency") + tcp.get("credit_in_account_currency")
			jv_map[index].root_type = spv.get("root_type")
			jv_map[index]["credit_in_account_currency"] = tcp.get("credit_in_account_currency")
			jv_map[index]["debit_in_account_currency"] = tcp.get("debit_in_account_currency")
			index += 1

	return jv_map

###################################################################################################################################
# CASH ACCOUNTING #
###################################################################################################################################

def get_value_added_tax_cash_accounting(filters, conditions, account_head, conditions_payment_entry, conditions_date_gl, taxes, base_tax_sum_taxes_si, base_tax_sum_taxes_pi, cond_jv_roottype_not_equity):
	""" to get sales/purchase invoices and return to prepare_data function """
	if account_head == "Invoices with no tax": # the invoices that don't have a tax account involved
		taxes_exceptions = taxes.replace("and tabAccount.name in", "")

		return (get_si_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions) +
			get_si_new_payment_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions) +
			get_pi_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions) +
			get_pi_new_payment_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions) +
            get_jv_tax_total_cash(filters, conditions, account_head, cond_jv_roottype_not_equity))
	else:
		return (get_si_tax_total_cash_accounting(filters, conditions, account_head, base_tax_sum_taxes_si) +
			get_si_new_payment_tax_total_cash_accounting(filters, account_head, conditions_payment_entry, base_tax_sum_taxes_si) +
			get_pi_tax_total_cash_accounting(filters, conditions, account_head, base_tax_sum_taxes_pi) +
			get_pi_new_payment_tax_total_cash_accounting(filters, account_head, conditions_payment_entry, base_tax_sum_taxes_pi) +
			get_jv_tax_total_cash(filters, conditions, account_head, cond_jv_roottype_not_equity))

def get_si_tax_total_cash_accounting(filters, conditions, account_head, base_tax_sum_taxes_si, excluded=""):
	""" to get the sales amounts of Cash Accounting """
	fields = """concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no,
       (`tabJournal Entry Account`.credit_in_account_currency / `tabSales Invoice`.base_grand_total)
       * base_tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid,
       `tabJournal Entry Account`.credit_in_account_currency as sales_value, 0.0 as purchase_value,
       `tabJournal Entry`.posting_date, account_name, total_taxes_and_charges, base_grand_total as grand_total,
       base_grand_total as sv, 0.0 as pv, 0 as part_total_payment, {base_tax_sum_taxes_si}
       """.format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

	just_payments = """and ( not exists (
        select debit
        from `tabJournal Entry Account`
        where parent = voucher_no and ((account_type in ('Income Account', 'Chargeable', 'Expense Account'))
        and debit > 0.0)
        and ( select count(account_type)
        from `tabJournal Entry Account`
        where parent = voucher_no and (account_type = 'Receivable' and credit > 0.0))))"""

	part_total_payment = """, (select IF(IF(tjea.debit_in_account_currency > 0, tjea.debit_in_account_currency, 
			tjea.credit_in_account_currency) < tsi.base_grand_total, 1, 0) as part_total_payment
			from `tabJournal Entry Account` tjea
			inner join `tabSales Invoice` tsi on tsi.name = tjea.reference_name
			where tjea.reference_name = voucher_no and tjea.parent = `tabJournal Entry`.name
			group by part_total_payment) as part_total_payment"""

	return frappe.db.sql("""select {fields}{part_total_payment}
		from `tabGL Entry`
		left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
		left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
		left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		where account_head in ('{account_head}')
		and `tabJournal Entry Account`.parent in (select distinct voucher_no
			from `tabGL Entry`
			where voucher_type = 'Journal Entry'
			and `tabGL Entry`.party_type = 'Customer'
			{just_payments}
			{conditions}
			{excluded})
		group by `tabJournal Entry Account`.parent, `tabSales Invoice`.name, `tabJournal Entry Account`.name
		order by posting_date, voucher_no
		""".format(conditions=conditions,
	               fields=fields,
	               just_payments=just_payments,
	               account_head=account_head,
	               excluded=excluded,
	               part_total_payment=part_total_payment),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

def get_si_new_payment_tax_total_cash_accounting(filters, account_head, conditions_payment_entry, base_tax_sum_taxes_si, excluded=""):
	""" to get the sales (payment tables) amounts of Cash Accounting """
	fields = """concat(voucher_no, ': ', `tabSales Invoice`.title) as voucher_no,
		(allocated_amount  / `tabSales Invoice`.base_grand_total) *	base_tax_amount_after_discount_amount as tax_collected,
		0.0 as tax_paid, allocated_amount as sales_value, 0.0 as purchase_value, `tabPayment Entry`.posting_date, account_name,
		total_taxes_and_charges, base_grand_total as grand_total, base_grand_total as sv, 0.0 as pv,
		IF(allocated_amount < total_amount, 1, 0) as part_total_payment, {base_tax_sum_taxes_si}
		""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

	return frappe.db.sql("""select {fields}
		from `tabGL Entry`
		left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabGL Entry`.voucher_no
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabSales Invoice` on `tabSales Invoice`.name = `tabGL Entry`.voucher_no
		left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
		left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
		where account_head in ('{account_head}')
		and `tabGL Entry`.voucher_type in ('Sales Invoice')
		and `tabPayment Entry`.docstatus = 1
		{conditions_payment_entry}
		{excluded}
		and root_type = 'Income'
		group by reference_name, `tabPayment Entry`.name
		order by posting_date, voucher_no
		""".format(conditions_payment_entry=conditions_payment_entry, fields=fields, account_head=account_head, excluded=excluded),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

def get_pi_tax_total_cash_accounting(filters, conditions, account_head, base_tax_sum_taxes_pi, excluded=""):
	""" to get the purchase amounts of Cash Accounting """
	fields = """concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected, if((select count(*) as cn
		from `tabPurchase Taxes and Charges` where parent = voucher_no and account_head in ('{account_head}')) > 1,(
		((select sum(if(add_deduct_tax = 'Deduct', base_tax_amount_after_discount_amount * -1,
		base_tax_amount_after_discount_amount)) from `tabPurchase Taxes and Charges` where
		`tabPurchase Taxes and Charges`.account_head in ('{account_head}') and `tabPurchase Taxes and Charges`.parent = voucher_no)
		) + (select	ifnull(Sum(PI.total_taxes_and_charges), 0) from `tabPurchase Invoice` PI where
		PI.return_against = voucher_no)), (if (add_deduct_tax = 'Deduct', (`tabJournal Entry Account`.debit_in_account_currency
		/ `tabPurchase Invoice`.base_grand_total) * base_tax_amount_after_discount_amount * -1,
		(`tabJournal Entry Account`.debit_in_account_currency / `tabPurchase Invoice`.base_grand_total)
		* base_tax_amount_after_discount_amount))) as tax_paid, 0.0 as sales_value,
		(select sum(jea.debit_in_account_currency) from `tabJournal Entry Account` jea	where jea.reference_name = voucher_no
		and jea.parent = `tabJournal Entry Account`.parent) as purchase_value, `tabJournal Entry`.posting_date, account_name,
		total_taxes_and_charges, base_grand_total as grand_total, 0.0 as sv, base_grand_total as pv, {base_tax_sum_taxes_pi}
		""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi, account_head=account_head)

	just_payments = """and ( not exists ( select credit
		from `tabJournal Entry Account`
		left join tabAccount on tabAccount.account_type = `tabJournal Entry Account`.account_type
		where `tabJournal Entry Account`.parent = voucher_no and root_type = 'Expense' and credit > 0.0
		and ( select count(`tabJournal Entry Account`.account_type)
		from `tabJournal Entry Account`
		where parent = voucher_no and debit > 0.0) > 0))"""

	part_total_payment = """, (select IF(IF(tjea.debit_in_account_currency > 0, tjea.debit_in_account_currency, 
		tjea.credit_in_account_currency) < tpi.base_grand_total, 1, 0) as part_total_payment
		from `tabJournal Entry Account` tjea
		inner join `tabPurchase Invoice` tpi on tpi.name = tjea.reference_name
		where tjea.reference_name = voucher_no and tjea.parent = `tabJournal Entry`.name
		group by part_total_payment) as part_total_payment"""

	return frappe.db.sql("""select {fields}{part_total_payment}
		from `tabGL Entry`
		left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
		left join `tabJournal Entry Account` on `tabJournal Entry Account`.reference_name = voucher_no
		left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		where account_head in ('{account_head}')
		and `tabJournal Entry Account`.parent in (select distinct voucher_no
			from `tabGL Entry`
			where voucher_type = 'Journal Entry'
			and `tabGL Entry`.party_type = 'Supplier'
			{just_payments}
			{conditions}
			{excluded})
		{invoice_with_no_income_expense}
		group by `tabJournal Entry Account`.parent, `tabPurchase Invoice`.name
		order by posting_date, voucher_no
		""".format(conditions=conditions,
	               fields=fields,
	               just_payments=just_payments,
	               account_head=account_head,
	               excluded=excluded,
	               part_total_payment=part_total_payment,
	               invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense("""`tabPurchase Invoice`.name""")),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

def get_pi_new_payment_tax_total_cash_accounting(filters, account_head, conditions_payment_entry, base_tax_sum_taxes_pi, excluded=""):
	""" to get the purchase (payment tables) amounts of Cash Accounting """
	fields = """concat(voucher_no, ': ', `tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected,
		SUM(if(add_deduct_tax = 'Deduct', (allocated_amount / `tabPurchase Invoice`.base_grand_total) *
			base_tax_amount_after_discount_amount * -1, (allocated_amount / `tabPurchase Invoice`.base_grand_total) *
			base_tax_amount_after_discount_amount)) as tax_paid, 0.0 as sales_value, allocated_amount as purchase_value,
		`tabPayment Entry`.posting_date, account_name, total_taxes_and_charges, base_grand_total as grand_total, 0.0 as sv,
		base_grand_total as pv, IF(allocated_amount < total_amount, 1, 0) as part_total_payment, {base_tax_sum_taxes_pi}
		""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi)

	return frappe.db.sql("""select {fields}
		from `tabGL Entry`
		left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabGL Entry`.voucher_no
		left join tabAccount on tabAccount.name = `tabGL Entry`.account
		left join `tabPurchase Invoice` on `tabPurchase Invoice`.name = `tabGL Entry`.voucher_no
		left join `tabPayment Entry Reference` on `tabPayment Entry Reference`.reference_name = voucher_no
		left join `tabPayment Entry` on `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
		where account_head in ('{account_head}')
		and `tabGL Entry`.voucher_type in ('Purchase Invoice')
		and `tabPayment Entry`.docstatus = 1
		{invoice_with_no_income_expense}
		{conditions_payment_entry}
		{excluded}
		and tabAccount.account_name = 'Creditors'
		group by reference_name, `tabPayment Entry`.name
		order by posting_date, voucher_no
		""".format(conditions_payment_entry=conditions_payment_entry, fields=fields, account_head=account_head, excluded=excluded,
					invoice_with_no_income_expense=get_cond_invoice_with_no_income_expense("""`tabPurchase Invoice`.name""")),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

def get_jv_tax_total_cash(filters, conditions, account_head, cond_jv_roottype_not_equity, excluded=""):
	""" to get the journal vouchers amounts of Cash Accounting """
	jv_fields = """voucher_no as journal_voucher, concat(voucher_no, ': ', title) as voucher_no,
		`tabJournal Entry`.posting_date, account_name, 0.0 as total_taxes_and_charges, 0.0 as grand_total,
		0.0 as base_tax_amount_after_discount_amount, voucher_no as invoice, 0.0 as sales_value, 0.0 as purchase_value,
		`tabJournal Entry`.total_debit as sv, `tabJournal Entry`.total_credit as pv, 0 as part_total_payment"""

	# to get tax collected and paid
	jv_map = frappe.db.sql("""select {jv_fields}
	        from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
			where `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
			and `tabGL Entry`.account in ('{account_head}')
			and `tabJournal Entry`.docstatus = 1
			and `tabJournal Entry Account`.parent in (select `tabJournal Entry Account`.parent
				from `tabJournal Entry Account`
				left join tabAccount on tabAccount.name = `tabJournal Entry Account`.account
				left join `tabJournal Entry` on `tabJournal Entry`.name = `tabJournal Entry Account`.parent
				where `tabJournal Entry Account`.docstatus = 1
				{conditions}
				{excluded}
				and tabAccount.account_type in ('Bank', 'Cash'))
			{jv_roottype_not_equity}
			{conditions}
			{excluded}
			and (select Count(*) as GLE_Rows_Qty from `tabGL Entry` gle where gle.voucher_no = `tabGL Entry`.voucher_no) > 2
			group by voucher_no
			order by posting_date, voucher_no
			""".format(conditions=conditions, jv_fields=jv_fields, jv_roottype_not_equity=cond_jv_roottype_not_equity,
	                   account_head=account_head, excluded=excluded),
			{
			   "company": filters.company,
			   "from_date": filters.from_date,
			   "to_date": filters.to_date
			}, as_dict=True)

	invoices = ""
	for invoice in jv_map:
		invoices += "'" + invoice.journal_voucher + "',"

	if invoices != "":
		invoices = invoices[:len(invoices) - 1]

	if jv_map:
		# to get sales and purchase values
		sales_purchase_values = frappe.db.sql("""select total_debit as sales_value, if(SUM(debit_in_account_currency) = 0,
			SUM(credit_in_account_currency), SUM(debit_in_account_currency)) as purchase_value, root_type,
			concat(`tabJournal Entry`.name, ': ', title) as voucher_no
			from `tabJournal Entry Account`
		    left join tabAccount ON tabAccount.name = `tabJournal Entry Account`.account
		    left join `tabJournal Entry` ON `tabJournal Entry`.name = `tabJournal Entry Account`.parent
		    where report_type = 'Profit and Loss'
		    and `tabJournal Entry Account`.parent in ({invoices})
			group by voucher_no
			order by `tabJournal Entry`.posting_date, voucher_no""".format(invoices=invoices),
				{
					"company": filters.company,
					"from_date": filters.from_date,
					"to_date": filters.to_date
				}, as_dict=True)

		# to get debit and credit to use as tax paid/collected
		tax_collected_paid = frappe.db.sql("""
			select voucher_no, `tabGL Entry`.debit_in_account_currency, `tabGL Entry`.credit_in_account_currency
			from `tabGL Entry`
			left join tabAccount on tabAccount.name = `tabGL Entry`.account
			left join `tabJournal Entry` on `tabJournal Entry`.name = `tabGL Entry`.voucher_no
			left join `tabJournal Entry Account` on `tabJournal Entry Account`.parent = voucher_no
			where `tabJournal Entry Account`.parent in ({invoices})
			and `tabGL Entry`.account in ('{account_head}')
			group by voucher_no
			order by `tabJournal Entry`.posting_date, voucher_no
			""".format(invoices=invoices, account_head=account_head, excluded=excluded), as_dict=True)

		index = 0
		# update de values to return the data mapped
		# for spv in sales_purchase_values:
		for spv, tcp in zip(sales_purchase_values, tax_collected_paid):
			jv_map[index].sales_value = spv.get("sales_value")
			jv_map[index].purchase_value = \
				spv.get("purchase_value") + tcp.get("debit_in_account_currency") + tcp.get("credit_in_account_currency")
			jv_map[index].root_type = spv.get("root_type")
			jv_map[index]["credit_in_account_currency"] = tcp.get("credit_in_account_currency")
			jv_map[index]["debit_in_account_currency"] = tcp.get("debit_in_account_currency")
			index += 1

	return jv_map

###############################
# INVOICES WITH NO GL ENTRIES #
###############################

def get_sinv_tax_total_invoices_with_no_gl_entries_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_si, excluded=""):
	""" to get the amounts of some Sales Invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabGL Entry`.", "")

	fields = """concat(`tabSales Invoice`.name, ': ', title) as voucher_no,
		base_tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid, posting_date, account_name,
		total_taxes_and_charges, base_grand_total as grand_total, base_grand_total as sales_value, 0.0 as purchase_value,
		base_grand_total as sv, 0.0 as pv, {base_tax_sum_taxes_si}""".format(base_tax_sum_taxes_si=base_tax_sum_taxes_si)

	return frappe.db.sql("""select {fields}
			from `tabSales Invoice`
			left join `tabSales Taxes and Charges` on `tabSales Taxes and Charges`.parent = `tabSales Invoice`.name
			left join tabAccount on tabAccount.name = `tabSales Taxes and Charges`.account_head
			where `tabSales Invoice`.base_discount_amount = (tax_amount + `tabSales Invoice`.total)
			and `tabSales Invoice`.docstatus = 1
			and account_head in ('{account_head}')
			{conditions}
			{excluded}
			group by voucher_no
			""".format(conditions=conditions, fields=fields, account_head=account_head, excluded=excluded),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

def get_pinv_tax_total_invoices_with_no_gl_entries_accrual_accounting(filters, conditions, account_head, base_tax_sum_taxes_pi, excluded=""):
	""" to get the amounts of some Purchase Invoices that don't have gl entries and should be shown in the report """
	conditions = conditions.replace("`tabGL Entry`.", "")

	fields = """concat(`tabPurchase Invoice`.name, ': ', title) as voucher_no,
		base_tax_amount_after_discount_amount as tax_collected, 0.0 as tax_paid, posting_date, account_name,
		total_taxes_and_charges, base_grand_total as grand_total, 0.0 as sales_value, base_grand_total as purchase_value, 0.0 as sv,
		base_grand_total as pv, {base_tax_sum_taxes_pi}""".format(base_tax_sum_taxes_pi=base_tax_sum_taxes_pi)

	return frappe.db.sql("""select {fields}
			from `tabPurchase Invoice`
			left join `tabPurchase Taxes and Charges` on `tabPurchase Taxes and Charges`.parent = `tabPurchase Invoice`.name
			left join tabAccount on tabAccount.name = `tabPurchase Taxes and Charges`.account_head
			where `tabPurchase Invoice`.base_discount_amount = (tax_amount + `tabPurchase Invoice`.total)
			and `tabPurchase Invoice`.docstatus = 1
			and account_head in ('{account_head}')
			{conditions}
			{excluded}
			group by voucher_no
			order by posting_date, voucher_no
			""".format(conditions=conditions, fields=fields, account_head=account_head, excluded=excluded),
			{
				"company": filters.company,
				"from_date": filters.from_date,
				"to_date": filters.to_date
			}, as_dict=True)

########################
# INVOICES WITH NO TAX #
########################

def get_si_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions):
	""" to get the sales amounts of Cash Accounting when the invoice has no tax """
	fields = """concat(`tabJournal Entry Account`.reference_name, ': ',
		`tabSales Invoice`.title) as voucher_no, 0.0 as tax_collected, 0.0 as tax_paid,
		`tabJournal Entry Account`.credit_in_account_currency sales_value, 0.0 as purchase_value,
		`tabGL Entry`.posting_date, account_name, `tabJournal Entry Account`.credit_in_account_currency total_taxes_and_charges,
        `tabJournal Entry Account`.credit_in_account_currency as grand_total,
	    `tabJournal Entry Account`.credit_in_account_currency as base_tax_amount_after_discount_amount"""

	return frappe.db.sql("""select {fields}
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
		order by posting_date, voucher_no
		""".format(fields=fields,
                   taxes_exceptions=taxes_exceptions,
                   conditions_date_gl=conditions_date_gl),
                 {
                     "company": filters.company,
                     "from_date": filters.from_date,
                     "to_date": filters.to_date
                 }, as_dict=True)

def get_si_new_payment_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions):
	""" to get the sales amounts (payment tables) of Cash Accounting when the invoice has no tax """
	fields = """concat(reference_name, ': ', `tabSales Invoice`.title) as voucher_no,
		0.0 as tax_collected, 0.0 as tax_paid, allocated_amount as sales_value, 0.0 as purchase_value,
		`tabGL Entry`.posting_date,	account_name, total_taxes_and_charges, base_grand_total as grand_total,
		base_grand_total as base_tax_amount_after_discount_amount"""

	return frappe.db.sql("""select {fields}
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
		order by posting_date, voucher_no
		""".format(fields=fields,
                   taxes_exceptions=taxes_exceptions,
                   conditions_date_gl=conditions_date_gl),
                 {
                     "company": filters.company,
                     "from_date": filters.from_date,
                     "to_date": filters.to_date
                 }, as_dict=True)

def get_pi_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions):
	""" to get the purchase amounts of Cash Accounting when the invoice has no tax """
	fields = """concat(`tabJournal Entry Account`.reference_name, ': ',
		`tabPurchase Invoice`.title) as voucher_no, 0.0 as tax_collected, 0.0 as tax_paid,
		0.0 as sales_value, `tabJournal Entry Account`.debit_in_account_currency as purchase_value,
		`tabGL Entry`.posting_date, account_name, `tabJournal Entry Account`.debit_in_account_currency total_taxes_and_charges,
        `tabJournal Entry Account`.debit_in_account_currency as grand_total,
	    `tabJournal Entry Account`.debit_in_account_currency as base_tax_amount_after_discount_amount"""

	return frappe.db.sql("""select {fields}
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
		order by posting_date, voucher_no
		""".format(fields=fields,
                   taxes_exceptions=taxes_exceptions,
                   conditions_date_gl=conditions_date_gl),
                 {
                     "company": filters.company,
                     "from_date": filters.from_date,
                     "to_date": filters.to_date
                 }, as_dict=True)

def get_pi_new_payment_tax_total_invoices_with_no_tax_cash_accounting(filters, conditions_date_gl, taxes_exceptions):
	""" to get the purchase amounts (payment tables) of Cash Accounting when the invoice has no tax """
	fields = """concat(reference_name, ': ', `tabPurchase Invoice`.title) as voucher_no,
		0.0 as tax_collected, 0.0 as tax_paid, 0.0 as sales_value, allocated_amount as purchase_value,
		`tabGL Entry`.posting_date,	account_name, total_taxes_and_charges, base_grand_total as grand_total,
		base_grand_total as base_tax_amount_after_discount_amount"""

	return frappe.db.sql("""select {fields}
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
		""".format(fields=fields,
                   taxes_exceptions=taxes_exceptions,
                   conditions_date_gl=conditions_date_gl),
                 {
                     "company": filters.company,
                     "from_date": filters.from_date,
                     "to_date": filters.to_date
                 }, as_dict=True)