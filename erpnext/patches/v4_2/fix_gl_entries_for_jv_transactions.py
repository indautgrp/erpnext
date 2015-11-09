# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe

def execute():
	jv_vouchers = frappe.db.sql("""select 'Journal Voucher',name from `tabJournal Voucher` where name in (
                select distinct c.parent from (
                select parent,account, cost_center,count(distinct project_name),count(distinct support_ticket)
                from `tabJournal Voucher Detail`
                where (project_name is not null or support_ticket is not null)
                and account in (select name from tabAccount where report_type='Profit and Loss')
                group by parent,account,cost_center
                having count(distinct project_name)>1 or count(distinct support_ticket)>1) as c) and docstatus=1""" )
    
	rejected=[]
	for voucher_type,voucher_no in jv_vouchers:

		try:
            		print voucher_type,voucher_no
			frappe.db.sql("""delete from `tabGL Entry`
			where voucher_no=%s""", (voucher_no))

			voucher = frappe.get_doc(voucher_type, voucher_no)
			voucher.make_gl_entries()
			frappe.db.commit()

		except Exception, e:
			print frappe.get_traceback()
			rejected.append([voucher_no])
			frappe.db.rollback()
	
	print "Failed to recreate: "
	print rejected
