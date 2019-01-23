// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

{% include 'erpnext/controllers/js/contact_address_common.js' %};

frappe.ui.form.on("Address", "validate", function(frm) {
	// Check when save an address if the email, phone number or fax is already registered in another address,
	// and shows a popup to the user whit links to the address
	frappe.call({
			method: 'erpnext.utilities.transaction_base.check_address_email_phone_fax_already_exist',
			args: {
				email_id: frm.doc.email_id,
				phone: frm.doc.phone,
				fax: frm.doc.fax,
				name: frm.doc.name
			},
			callback: function (r) {
				if (r.message) {
					
					var variant = r.message;
					var values = "";						
					var addresses = variant.split(",");
					
					for (var i=0; i < addresses.length; i++) {
						var address_field = addresses[i].split(";"); // position [1]
						var address = address_field[0].split(":");
						
						var link = repl('<a target="_blank" href="#Form/' + address_field[1] + '/%(name)s"' +
								'class="strong variant-click">%(label)s</a>', {
							name: encodeURIComponent(address[1]),
							label: address[1]
						});
						
						var address_label = address[0].split("/");
						
						if (address_label[0] == "Email ID")
							values += "Email ID " + frm.doc.email_id + " is already in use on " + address_field[1] +
									": " + link + " as an " + address_label[1] + "<br>";
						else if (address_label[0] == "Phone")
							values += "Phone " + frm.doc.phone + " is already in use on " + address_field[1] +
									": "+ link + " as a " + address_label[1] + "<br>";
						else
							values += "Fax " + frm.doc.fax + " is already in use on " + address_field[1] +
									": " + link + " as a " + address_label[1] + "<br>";
					}
											
					frappe.msgprint(values);						
				}
			}
		});
	// clear linked customer / supplier / sales partner on saving...
	$.each(["Customer", "Supplier", "Sales Partner", "Lead"], function(i, doctype) {
		var name = frm.doc[doctype.toLowerCase().replace(/ /g, "_")];
		if(name && locals[doctype] && locals[doctype][name])
			frappe.model.remove_from_locals(doctype, name);
	});
});
