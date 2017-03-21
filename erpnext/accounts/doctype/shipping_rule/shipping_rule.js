// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

cur_frm.fields_dict['cost_center'].get_query = function(doc) {
	return{
		filters:{
			'company': doc.company,
			'is_group': 0
		}
	}
}