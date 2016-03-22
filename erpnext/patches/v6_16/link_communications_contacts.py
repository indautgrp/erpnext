from __future__ import unicode_literals
import frappe
from frappe import _
def execute():


	origin_contact = frappe.db.sql("select email_id,supplier,customer,user from `tabContact`",as_dict=1)
	origin_communication = frappe.db.sql("select name, sender,recipients from `tabCommunication`",as_dict=1)


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