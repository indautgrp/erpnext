from __future__ import unicode_literals
import frappe
def execute():
	frappe.reload_doctype("Communication")
	frappe.db.sql("update `tabContact` set email_id = lower(email_id)")
	frappe.db.sql("update `tabCommunication` set sender = lower(sender),recipients = lower(recipients)")
	origin_contact = frappe.db.sql("select email_id,supplier,customer,user from `tabContact`",as_dict=1)
	origin_communication = frappe.db.sql("select name, sender,recipients from `tabCommunication`",as_dict=1)

	for  communication in origin_communication:

		sender = communication["sender"]
		recipients = communication["recipients"]
		# format contacts
		for comm in origin_contact:
			if comm["user"] is None and comm["email_id"]:
				if (sender and sender.find(comm["email_id"]) > -1) or (recipients and recipients.find(comm["email_id"]) > -1):
					if comm["supplier"] and comm["customer"]:
						frappe.db.sql("""update `tabCommunication`
							set supplier = %(supplier)s,
							customer = %(customer)s
							where name = %(name)s""", {
							"supplier": comm["supplier"],
							"customer": comm["customer"],
							"name": communication["name"]
						})

					elif comm["supplier"]:
						frappe.db.sql("""update `tabCommunication`
							set supplier = %(supplier)s
							where name = %(name)s""", {
							"supplier": comm["supplier"],
							"name": communication["name"]
						})

					elif comm["customer"]:
						frappe.db.sql("""update `tabCommunication`
							set customer = %(customer)s
							where name = %(name)s""", {
							"customer": comm["customer"],
							"name": communication["name"]
						})
