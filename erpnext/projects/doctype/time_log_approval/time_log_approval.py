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

		dl = frappe.db.sql("""select name, employee_name, date_worked, hours,
					     activity_type, project, task, support_ticket, note, leave_application
			from
				`tabTime Log` 
			where
				date_worked >= %s and date_worked <= %s and docstatus=0
				order by date_worked DESC, name DESC""" %
				('%s', '%s'), (self.from_date, self.to_date), as_dict=1)

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

	def approve_time_log(self):
		time_logs = []
		for d in self.get('time_log_list'):

			if d.approved:
				time_log = frappe.get_doc('Time Log', d.time_log_id)
				time_log.submit()
				frappe.db.set_value("Time Log", d.time_log_id, "workflow_state", "Approved")
				time_logs.append(d.time_log_id)
		
		self.get_details()

		if time_logs:
			msgprint("Approved time log: {0}".format(", ".join(time_logs)))
		else:
			msgprint(_("No time log approved"))

			
