from __future__ import unicode_literals
import frappe
from frappe import _
from calendar import monthrange

def execute():
	sql = """select employee, month, fiscal_year, status, employee_name, name
		from `tabSalary Slip`
		where start_date is null
		and end_date is null"""

	for date in frappe.db.sql(sql, as_dict=True):
		years = date.fiscal_year.split("-")
		if int(date.month) >= 7:
			year = years[0]
		else:
			year = years[1]
		start_date = year + "-" + date.month + "-01"
		end_date = year + "-" + date.month + "-" + str(monthrange(int(year), int(date.month))[1])
		if date.docstatus == 0:
			status = "Draft"
		elif date.docstatus == 1:
			status = "Submitted"
		else:
			status = "Cancelled"

		frappe.db.sql("""update `tabSalary Slip`
			set start_date = %(start_date)s, end_date = %(end_date)s, status = %(status)s,
				salary_structure = %(salary_structure)s
			where employee = %(employee)s
			and month = %(month)s
			and fiscal_year = %(fiscal_year)s
			and name = %(name)s""",{"start_date": start_date,
		                            "end_date": end_date,
		                            "employee": date.employee,
		                            "month": date.month,
		                            "fiscal_year": date.fiscal_year,
		                            "name": date.name,
                                    "status": status,
                                    "salary_structure": date.employee_name}, as_dict=1)