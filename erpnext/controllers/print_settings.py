# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

def print_settings_for_item_table(doc):
	doc.print_templates = {
		"description": "templates/print_formats/includes/item_table_description.html",
		"qty": "templates/print_formats/includes/item_table_qty.html",
		"price_list_rate": "templates/print_formats/includes/item_table_price_list_rate.html",
		"rate": "templates/print_formats/includes/item_table_rate.html",
		"amount": "templates/print_formats/includes/item_table_amount.html"
	}
	doc.hide_in_print_layout = ["item_code", "item_name", "image", "uom", "stock_uom"]
