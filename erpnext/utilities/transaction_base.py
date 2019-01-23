# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
import frappe.share
from frappe import _
from frappe.utils import cstr, now_datetime, cint, flt
from erpnext.controllers.status_updater import StatusUpdater

class UOMMustBeIntegerError(frappe.ValidationError): pass

class TransactionBase(StatusUpdater):
	def load_notification_message(self):
		dt = self.doctype.lower().replace(" ", "_")
		if int(frappe.db.get_value("Notification Control", None, dt) or 0):
			self.set("__notification_message",
				frappe.db.get_value("Notification Control", None, dt + "_message"))

	def validate_posting_time(self):
		if not self.posting_time:
			self.posting_time = now_datetime().strftime('%H:%M:%S')

	def add_calendar_event(self, opts, force=False):
		if cstr(self.contact_by) != cstr(self._prev.contact_by) or \
				cstr(self.contact_date) != cstr(self._prev.contact_date) or force:

			self.delete_events()
			self._add_calendar_event(opts)

	def delete_events(self):
		events = frappe.db.sql_list("""select name from `tabEvent`
			where ref_type=%s and ref_name=%s""", (self.doctype, self.name))
		if events:
			frappe.db.sql("delete from `tabEvent` where name in (%s)"
				.format(", ".join(['%s']*len(events))), tuple(events))

			frappe.db.sql("delete from `tabEvent Role` where parent in (%s)"
				.format(", ".join(['%s']*len(events))), tuple(events))

	def _add_calendar_event(self, opts):
		opts = frappe._dict(opts)

		if self.contact_date:
			event = frappe.get_doc({
				"doctype": "Event",
				"owner": opts.owner or self.owner,
				"subject": opts.subject,
				"description": opts.description,
				"starts_on":  self.contact_date,
				"event_type": "Private",
				"ref_type": self.doctype,
				"ref_name": self.name
			})

			event.insert(ignore_permissions=True)

			if frappe.db.exists("User", self.contact_by):
				frappe.share.add("Event", event.name, self.contact_by,
					flags={"ignore_share_permission": True})

	def validate_uom_is_integer(self, uom_field, qty_fields):
		validate_uom_is_integer(self, uom_field, qty_fields)

	def validate_with_previous_doc(self, ref):
		for key, val in ref.items():
			is_child = val.get("is_child_table")
			ref_doc = {}
			item_ref_dn = []
			for d in self.get_all_children(self.doctype + " Item"):
				ref_dn = d.get(val["ref_dn_field"])
				if ref_dn:
					if is_child:
						self.compare_values({key: [ref_dn]}, val["compare_fields"], d)
						if ref_dn not in item_ref_dn:
							item_ref_dn.append(ref_dn)
						elif not val.get("allow_duplicate_prev_row_id"):
							frappe.throw(_("Duplicate row {0} with same {1}").format(d.idx, key))
					elif ref_dn:
						ref_doc.setdefault(key, [])
						if ref_dn not in ref_doc[key]:
							ref_doc[key].append(ref_dn)
			if ref_doc:
				self.compare_values(ref_doc, val["compare_fields"])

	def compare_values(self, ref_doc, fields, doc=None):
		for reference_doctype, ref_dn_list in ref_doc.items():
			for reference_name in ref_dn_list:
				prevdoc_values = frappe.db.get_value(reference_doctype, reference_name,
					[d[0] for d in fields], as_dict=1)

				if not prevdoc_values:
					frappe.throw(_("Invalid reference {0} {1}").format(reference_doctype, reference_name))

				for field, condition in fields:
					if prevdoc_values[field] is not None:
						self.validate_value(field, condition, prevdoc_values[field], doc)


	def validate_rate_with_reference_doc(self, ref_details):
		for ref_dt, ref_dn_field, ref_link_field in ref_details:
			for d in self.get("items"):
				if d.get(ref_link_field):
					ref_rate = frappe.db.get_value(ref_dt + " Item", d.get(ref_link_field), "rate")

					if abs(flt(d.rate - ref_rate, d.precision("rate"))) >= .01:
						frappe.throw(_("Row #{0}: Rate must be same as {1}: {2} ({3} / {4}) ")
							.format(d.idx, ref_dt, d.get(ref_dn_field), d.rate, ref_rate))

	def get_link_filters(self, for_doctype):
		if hasattr(self, "prev_link_mapper") and self.prev_link_mapper.get(for_doctype):
			fieldname = self.prev_link_mapper[for_doctype]["fieldname"]
			
			values = filter(None, tuple([item.as_dict()[fieldname] for item in self.items]))

			if values:
				ret = {
					for_doctype : {
						"filters": [[for_doctype, "name", "in", values]]
					}
				}
			else:
				ret = None
		else:
			ret = None
		
		return ret

def delete_events(ref_type, ref_name):
	frappe.delete_doc("Event", frappe.db.sql_list("""select name from `tabEvent`
		where ref_type=%s and ref_name=%s""", (ref_type, ref_name)), for_reload=True)

def validate_uom_is_integer(doc, uom_field, qty_fields, child_dt=None):
	if isinstance(qty_fields, basestring):
		qty_fields = [qty_fields]

	distinct_uoms = list(set([d.get(uom_field) for d in doc.get_all_children()]))
	integer_uoms = filter(lambda uom: frappe.db.get_value("UOM", uom,
		"must_be_whole_number") or None, distinct_uoms)

	if not integer_uoms:
		return

	for d in doc.get_all_children(parenttype=child_dt):
		if d.get(uom_field) in integer_uoms:
			for f in qty_fields:
				if d.get(f):
					if cint(d.get(f))!=d.get(f):
						frappe.throw(_("Quantity cannot be a fraction in row {0}").format(d.idx), UOMMustBeIntegerError)

# ADDRESS #
@frappe.whitelist()
def check_address_email_phone_fax_already_exist(email_id="", phone="", fax="", name=""):
	'''Check when save an address if the email, phone number or fax is already registered in another address'''
	email_id = email_id.strip()
	phone = phone.strip()
	fax = fax.strip()
	name = name.strip()

	email_id_address = check_address_email_already_exist(email_id, name)
	phone_address = check_address_phone_number_already_exist(phone, name)
	fax_address = check_address_fax_already_exist(fax, name)

	# for cross checking on contact
	email_id_contact = check_contact_email_already_exist(email_id, name)
	phone_contact = check_contact_phone_number_already_exist(phone, name)
	mobile_no_contact = check_contact_mobile_number_already_exist(fax, name)

	return_addresses = email_id_address + email_id_contact + phone_address + phone_contact + fax_address + mobile_no_contact

	if return_addresses != "":
		return_addresses = return_addresses[:-1]

	return return_addresses

def check_address_email_already_exist(email_id="", name=""):
	m_return = ""
	if email_id != "":
		addresses = frappe.db.sql("""select name from `tabAddress` where trim(email_id) = %s
			and name <> %s""", (email_id, name), as_dict=True)
		for address in addresses:
			m_return += "Email ID/Email ID" + ":" + address.name + ";Address" + ","

	return m_return

def check_address_phone_number_already_exist(phone="", name=""):
	m_return = ""
	if phone != "":
		addresses_phone = frappe.db.sql("""select name from `tabAddress` where replace(trim(phone), ' ', '') = %s and name <> %s""",
		                          (phone.replace(" ", ""), name), as_dict=True)
		for address_phone in addresses_phone:
			m_return += "Phone/Phone" + ":" + address_phone.name + ";Address" + ","

		addresses_fax = frappe.db.sql("""select name from `tabAddress` where replace(trim(fax), ' ', '') = %s and name <> %s""",
		                          (phone.replace(" ", ""), name), as_dict=True)
		for address_fax in addresses_fax:
			m_return += "Phone/Fax" + ":" + address_fax.name + ";Address" + ","

	return m_return

def check_address_fax_already_exist(fax="", name=""):
	m_return = ""
	if fax != "":
		addresses_fax = frappe.db.sql("""select name from `tabAddress` where replace(trim(fax), ' ', '') = %s and name <> %s""",
		                          (fax.replace(" ", ""), name), as_dict=True)
		for address_fax in addresses_fax:
			m_return += "Fax/Fax" + ":" + address_fax.name + ";Address" + ","

		addresses_phone = frappe.db.sql("""select name from `tabAddress` where replace(trim(phone), ' ', '') = %s and name <> %s""",
		                          (fax.replace(" ", ""), name), as_dict=True)
		for address_phone in addresses_phone:
			m_return += "Fax/Phone" + ":" + address_phone.name + ";Address" + ","

	return m_return

# CONTACT #
@frappe.whitelist()
def check_contact_email_phone_mobile_number_already_exist(email_id="", phone="", mobile_no="", name=""):
	'''Check when save a contact if the email, phone number or mobile number is already registered in another contact'''
	email_id = email_id.strip()
	phone = phone.strip()
	mobile_no = mobile_no.strip()
	name = name.strip()

	email_id_contact = check_contact_email_already_exist(email_id, name)
	phone_contact = check_contact_phone_number_already_exist(phone, name)
	mobile_no_contact = check_contact_mobile_number_already_exist(mobile_no, name)

	# for cross checking on address
	email_id_address = check_address_email_already_exist(email_id, name)
	phone_address = check_address_phone_number_already_exist(phone, name)
	fax_address = check_address_fax_already_exist(mobile_no, name)

	return_contacts = email_id_contact + email_id_address + phone_contact + phone_address + mobile_no_contact + fax_address

	if return_contacts != "":
		return_contacts = return_contacts[:-1]

	return return_contacts

def check_contact_email_already_exist(email_id="", name=""):
	m_return = ""
	if email_id != "":
		contacts = frappe.db.sql("""select name from `tabContact` where trim(email_id) = %s and
			name <> %s""", (email_id, name), as_dict=True)
		for contact in contacts:
			m_return += "Email ID/Email ID" + ":" + contact.name + ";Contact" + ","

	return m_return

def check_contact_phone_number_already_exist(phone="", name=""):
	m_return = ""
	if phone != "":
		contacts_phone = frappe.db.sql("""select name from `tabContact` where replace(trim(phone), ' ', '') = %s and name <> %s""",
		                         (phone.replace(" ", ""), name), as_dict=True)
		for contact_phone in contacts_phone:
			m_return += "Phone/Phone" + ":" + contact_phone.name + ";Contact" + ","

		contacts_mobile_no = frappe.db.sql("""select name from `tabContact` where replace(trim(mobile_no), ' ', '') = %s and name <> %s""",
		                         (phone.replace(" ", ""), name), as_dict=True)
		for contact_mobile_no in contacts_mobile_no:
			m_return += "Phone/Mobile Number" + ":" + contact_mobile_no.name + ";Contact" + ","

	return m_return

def check_contact_mobile_number_already_exist(mobile_no="", name=""):
	m_return = ""
	if mobile_no != "":
		contacts_mobile_no = frappe.db.sql("""select name from `tabContact` where replace(trim(mobile_no), ' ', '') = %s and name <> %s""",
		                         (mobile_no.replace(" ", ""), name), as_dict=True)
		for contact_mobile_no in contacts_mobile_no:
			m_return += "Mobile Number/Mobile Number" + ":" + contact_mobile_no.name + ";Contact" + ","

		contacts_phone = frappe.db.sql("""select name from `tabContact` where replace(trim(phone), ' ', '') = %s and name <> %s""",
		                         (mobile_no.replace(" ", ""), name), as_dict=True)
		for contact_phone in contacts_phone:
			m_return += "Mobile Number/Phone" + ":" + contact_phone.name + ";Contact" + ","

	return m_return
