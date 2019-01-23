// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

{% include 'erpnext/controllers/js/contact_address_common.js' %};

cur_frm.email_field = "email_id";
frappe.ui.form.on("Contact", {
	refresh: function(frm) {
		if(!frm.doc.user && !frm.is_new() && frm.perm[0].write) {
			frm.add_custom_button(__("Invite as User"), function() {
				frappe.call({
					method: "erpnext.utilities.doctype.contact.contact.invite_user",
					args: {
						contact: frm.doc.name
					},
					callback: function(r) {
						frm.set_value("user", r.message);
					}
				});
			});
		}
	},
	validate: function(frm) {
		// Check when save a contact if the email, phone number or mobile number is already registered in another contact,
		// and shows a popup to the user whit links to the contact
		frappe.call({
			method: 'erpnext.utilities.transaction_base.check_contact_email_phone_mobile_number_already_exist',
			args: {
				email_id: frm.doc.email_id,
				phone: frm.doc.phone,
				mobile_no: frm.doc.mobile_no,
				name: frm.doc.name
			},
			callback: function (r) {
				if (r.message) {
					
					var variant = r.message;
					var values = "";						
					var contacts = variant.split(",");
					
					for (var i=0; i < contacts.length; i++) {
						var contact_field = contacts[i].split(";"); // position [1]
						var contact = contact_field[0].split(":");
						
						var link = repl('<a target="_blank" href="#Form/' + contact_field[1] + '/%(name)s"' +
								'class="strong variant-click">%(label)s</a>', {
							name: encodeURIComponent(contact[1]),
							label: contact[1]
						});
						
						var contact_label = contact[0].split("/");
						
						if (contact_label[0] == "Email ID")
							values += "Email ID " + frm.doc.email_id + " is already in use on " + contact_field[1] +
									": " + link + " as an " + contact_label[1] + "<br>";
						else if (contact_label[0] == "Phone")
							values += "Phone " + frm.doc.phone + " is already in use on " + contact_field[1] +
									": " + link + " as a " + contact_label[1] + "<br>";
						else
							values += "Mobile Number " + frm.doc.mobile_no + " is already in use on " + contact_field[1] +
									": " + link + " as a " + contact_label[1] + "<br>";
					}
											
					frappe.msgprint(values);						
				}
			}
		});
		//clear linked customer / supplier / sales partner on saving...
		$.each(["Customer", "Supplier", "Sales Partner"], function(i, doctype) {
			var name = frm.doc[doctype.toLowerCase().replace(/ /g, "_")];
			if(name && locals[doctype] && locals[doctype][name])
				frappe.model.remove_from_locals(doctype, name);
		});
	}
});
