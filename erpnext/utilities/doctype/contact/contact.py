# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import cstr
from frappe import _

from erpnext.controllers.status_updater import StatusUpdater

class Contact(StatusUpdater):
	def autoname(self):
		# concat first and last name
		self.name = " ".join(filter(None,
			[cstr(self.get(f)).strip() for f in ["first_name", "last_name"]]))

		# concat party name if reqd
		for fieldname in ("customer", "supplier", "sales_partner"):
			if self.get(fieldname):
				self.name = self.name + "-" + cstr(self.get(fieldname)).strip()
				break

	def validate(self):
		self.set_status()
		self.validate_primary_contact()
		self.set_user()
		self.update_communication_ref()

	def set_user(self):
		if not self.user and self.email_id:
			self.user = frappe.db.get_value("User", {"email": self.email_id})

	def validate_primary_contact(self):
		if self.is_primary_contact == 1:
			if self.customer:
				frappe.db.sql("update tabContact set is_primary_contact=0 where customer = %s",
					(self.customer))
			elif self.supplier:
				frappe.db.sql("update tabContact set is_primary_contact=0 where supplier = %s",
					 (self.supplier))
			elif self.sales_partner:
				frappe.db.sql("""update tabContact set is_primary_contact=0
					where sales_partner = %s""", (self.sales_partner))
		else:
			if self.customer:
				if not frappe.db.sql("select name from tabContact \
						where is_primary_contact=1 and customer = %s", (self.customer)):
					self.is_primary_contact = 1
			elif self.supplier:
				if not frappe.db.sql("select name from tabContact \
						where is_primary_contact=1 and supplier = %s", (self.supplier)):
					self.is_primary_contact = 1
			elif self.sales_partner:
				if not frappe.db.sql("select name from tabContact \
						where is_primary_contact=1 and sales_partner = %s",
						self.sales_partner):
					self.is_primary_contact = 1

	def on_trash(self):
		frappe.db.sql("""update `tabIssue` set contact='' where contact=%s""",
			self.name)

	def update_communication_ref(self):
		origin_communication = frappe.db.sql("select name, sender,recipients from `tabCommunication`",as_dict=1)

		if self.email_id:
			self.email_id = self.email_id.lower()
			comm = {"email_id":self.email_id,
			        "name":self.name,
						"supplier":self.supplier,
                        "supplier_name":self.supplier_name,
						"customer":self.customer,
			            "customer_name":self.customer_name
						}
			for communication in origin_communication:
				sender = communication["sender"]
				recipients = communication["recipients"]
				if comm["email_id"]:
					if (sender and sender.find(comm["email_id"]) > -1) or (recipients and recipients.find(comm["email_id"]) > -1):
						if comm["supplier"] and comm["customer"]:
							frappe.db.sql("""update `tabCommunication`
									set timeline_doctype = %(timeline_doctype)s,
									timeline_name = %(timeline_name)s,
									timeline_label = %(timeline_label)s
									where name = %(name)s""", {
								"timeline_doctype": "Contact",
								"timeline_name":comm["name"],
								"timeline_label":self.name,
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
								"timeline_name":comm["supplier"],
								"timeline_label":comm["supplier_name"],
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
								"timeline_name":comm["customer"],
								"timeline_label":comm["customer_name"],
								"name": communication["name"]
							})

@frappe.whitelist()
def invite_user(contact):
	contact = frappe.get_doc("Contact", contact)

	if not contact.email_id:
		frappe.throw(_("Please set Email ID"))

	if contact.has_permission("write"):
		user = frappe.get_doc({
			"doctype": "User",
			"first_name": contact.first_name,
			"last_name": contact.last_name,
			"email": contact.email_id,
			"user_type": "Website User",
			"send_welcome_email": 1
		}).insert(ignore_permissions = True)

		return user.name

@frappe.whitelist()
def get_contact_details(contact):
	contact = frappe.get_doc("Contact", contact)
	out = {
		"contact_person": contact.get("name"),
		"contact_display": " ".join(filter(None,
			[contact.get("first_name"), contact.get("last_name")])),
		"contact_email": contact.get("email_id"),
		"contact_mobile": contact.get("mobile_no"),
		"contact_phone": contact.get("phone"),
		"contact_designation": contact.get("designation"),
		"contact_department": contact.get("department")
	}
	return out
