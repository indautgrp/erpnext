# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import msgprint, _
from frappe.model.document import Document

class TimeLogApproval(Document):
	def get_details(self):
		if not (self.from_date and self.to_date):
			msgprint("From Date and To Date are Mandatory")
			return
		
		additional_conditions = ''
		if self.employee:
			additional_conditions = " and employee = %(employee)s"

		dl = frappe.db.sql("""select name, employee_name, date_worked, hours,
					     activity_type, project, task, support_ticket, note, leave_application, quotation_
			from
				`tabTime Log` 
			where
				date_worked >= %(from_date)s and date_worked <= %(to_date)s and docstatus=0 and workflow_state='Pending'
				{additional_conditions}
				order by date_worked DESC, name DESC""".format(additional_conditions=additional_conditions),
				{"from_date": self.from_date, "to_date": self.to_date, "employee": self.employee}, as_dict=1)
				
		self.set('time_log_list', [])

		for d in dl:
			nl = self.append('time_log_list', {})
			nl.time_log_id = d.name
			nl.employee_name = d.employee_name
			nl.date_worked = d.date_worked
			nl.hours = d.hours
			nl.activity_type = d.activity_type
			nl.project = d.project
			nl.task = d.task
			nl.support_ticket = d.support_ticket
			nl.note = d.note
			nl.leave_application = d.leave_application
			nl.quotation = d.quotation_

	def approve_time_log(self):
		time_logs_approved = []
		time_logs_rejected = []

		for d in self.get('time_log_list'):

			if d.approved:
				if self.has_action_permission('Approve'):
					time_log = frappe.get_doc('Time Log', d.time_log_id)
					time_log.submit()
					frappe.db.set_value("Time Log", d.time_log_id, "workflow_state", "Approved")
					time_logs_approved.append(d.time_log_id)
				else:
					msgprint("Not permitted to Approve")
			if d.rejected:
				if self.has_action_permission('Reject'):
					time_log = frappe.get_doc('Time Log', d.time_log_id)
					time_log.workflow_state = "Rejected"
					time_log.save()
					time_logs_rejected.append(d.time_log_id)
				else:
					msgprint("Not permitted to Reject")

		self.get_details()

		if time_logs_rejected or time_logs_approved:
			if (len(time_logs_approved)>0):
				msgprint("Approved time log: {0}".format(", ".join(time_logs_approved)))
			if (len(time_logs_rejected)>0):
				msgprint("Rejected time log: {0}".format(", ".join(time_logs_rejected)))
		else:
			msgprint(_("No time log approved or rejected"))

	def has_action_permission(self, action):
		
		user_roles = frappe.get_roles(frappe.session.user)
		has_action_permission = False

		for role in user_roles:
			
			result = frappe.db.sql("""select * from `tabWorkflow Transition` where parent='Tim log approval for Employees'
					and action = %s and allowed = %s""", (action, role), as_dict=1)
			if result:
				has_action_permission = True
				break

		return has_action_permission
