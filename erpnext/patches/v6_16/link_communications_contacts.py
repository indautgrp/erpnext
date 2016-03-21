from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
import sys
sys.path.append('/home/erpnext/frappe-bench/pycharm-debug.egg')
import pydevd

def execute():
	#frappe.db.sql("ALTER TABLE tabCommunication ADD (customer VARCHAR(140), supplier VARCHAR(140));")
	#frappe.db.sql("""update `tabCommunication` as com, `tabContact` as tact
	#					set com.customer = tact.customer,
	#						com.supplier = tact.supplier
	#					where substr(com.sender,  instr(com.sender,"<")+1,  if(instr(com.sender,"<")=0,  length(com.sender),length(com.sender)-1-instr(com.sender,"<"))) = tact.email_id
	#					and (tact.supplier is not null or tact.customer is not null or tact.user is not null);""")



	origin_contact = frappe.db.sql("select email_id,supplier,customer,user from `tabContact`",as_dict=1)
	origin_communication = frappe.db.sql("select name, sender,recipients from `tabCommunication`",as_dict=1)

	#pydevd.settrace('192.168.8.113', port=14000, stdoutToServer=True, stderrToServer=True)

	contact = []
	communication = []

	#format contacts
	for comm in origin_contact:
		if (comm["user"]==None):
			temp = {}
			temp["email_id"] = comm["email_id"]
			temp["supplier"] = comm["supplier"]
			temp["customer"] = comm["customer"]
			contact.append(temp)

	#format sender
	for comm in origin_communication:
		temp = {}
		if isinstance(comm["sender"],basestring) and comm["sender"].find("<")>-1:
			temp["name"] = comm["name"]
			temp["email"] = comm["sender"][comm["sender"].find("<")+1:comm["sender"].find(">")].lower() #not sure if lower needed
			communication.append(temp)

	#format reciepient
	for comm in origin_communication:
		if isinstance(comm["recipients"],basestring):
			for r in comm["recipients"].split(','):
				temp = {}
				temp["name"] =comm["name"]
				temp["email"] =r.lower() #not sure if lower needed
				communication.append(temp)

	for comm in communication:
		for tact in contact:
			#check each item and submit
			if tact["email_id"]==comm["email"]:
				if tact["supplier"]is not None:
					frappe.db.sql("""update `tabCommunication`
						set supplier = %(supplier)s
						where name = %(name)s""",{
						"supplier": tact["supplier"],
						"name": comm["name"]
					})
				elif tact["customer"]is not None:
					frappe.db.sql("""update `tabCommunication`
						set customer = %(customer)s
						where name = %(name)s""",{
						"customer": tact["customer"],
						"name": comm["name"]
					})
	passed = True