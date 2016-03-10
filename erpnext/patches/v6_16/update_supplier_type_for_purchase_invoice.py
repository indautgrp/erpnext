# Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe

def execute():
	frappe.db.sql("""update `tabPurchase Invoice` pi set supplier_type =
	    (select supplier_type from `tabSupplier` su where su.name=pi.supplier)""")
