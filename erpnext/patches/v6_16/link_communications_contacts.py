from __future__ import unicode_literals
import frappe
def execute():
	frappe.reload_doctype("Communication")

	frappe.db.sql("update `tabContact` set email_id = lower(email_id)")
	frappe.db.sql("update `tabCommunication` set sender = lower(sender),recipients = lower(recipients)")





	origin_contact = frappe.db.sql("select name,email_id,supplier,supplier_name,customer,customer_name,user from `tabContact`",as_dict=1)
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
											set timeline_doctype = %(timeline_doctype)s,
											timeline_name = %(timeline_name)s,
											timeline_label = %(timeline_label)s
											where name = %(name)s""", {
							"timeline_doctype": "Contact",
							"timeline_name": comm["name"],
							"timeline_label": comm["name"],
							"name": communication["name"]
						})

					elif comm["supplier"]:
						# return {"supplier": comm["supplier"], "customer": None}
						frappe.db.sql("""update `tabCommunication`
											set timeline_doctype = %(timeline_doctype)s,
											timeline_name = %(timeline_name)s,
											timeline_label = %(timeline_label)s
											where name = %(name)s""", {
							"timeline_doctype": "Supplier",
							"timeline_name": comm["supplier"],
							"timeline_label": comm["supplier_name"],
							"name": communication["name"]
						})

					elif comm["customer"]:
						# return {"supplier": None, "customer": comm["customer"]}
						frappe.db.sql("""update `tabCommunication`
											set timeline_doctype = %(timeline_doctype)s,
											timeline_name = %(timeline_name)s,
											timeline_label = %(timeline_label)s
											where name = %(name)s""", {
							"timeline_doctype": "Customer",
							"timeline_name": comm["customer"],
							"timeline_label": comm["customer_name"],
							"name": communication["name"]
						})