from __future__ import unicode_literals
import frappe

def Replace_String(mTuple):
    vet = mTuple.split(',')
    newStr = ""
    for x in vet:
        str = x.strip()
        if str == "net_total_export":
            str = "net_total"
        else:
            str = str
        #elif str == "total_tax":
        #    str = "base_total_taxes_and_charges"
        #elif str == "net_total":
        #    str = "base_net_total"
        #elif str == "grand_total":
        #    str = "base_grand_total"
        #elif str == "rounded_total":
        #    str = "base_rounded_total"
        #elif str == "in_words_export":
        #    str = "in_words"
        #elif str == "in_words_import":
        #    str = "in_words"
        #elif str == "in_words":
        #    str = "base_in_words"
        #elif str == "net_total_import":
        #    str = "net_total"
        #elif str == "grand_total_export":
        #    str = "grand_total"
        #elif str == "grand_total_import":
        #    str = "grand_total"
        #elif str == "other_charges_total":
        #    str = "base_total_taxes_and_charges"
        #elif str == "other_charges_added":
        #    str = "base_taxes_and_charges_added"
        #elif str == "rounded_total_export":
        #    str = "rounded_total"
        #elif str == "other_charges_deducted":
        #    str = "base_taxes_and_charges_deducted"
        #elif str == "other_charges_added_import":
        #    str = "taxes_and_charges_added"
        #elif str == "other_charges_total_export":
        #    str = "total_taxes_and_charges"
        #elif str == "other_charges_deducted_import":
        #    str = "taxes_and_charges_deducted"

        newStr = newStr + ','
        newStr = newStr + str

    newStr = newStr[1:len(newStr)]

    return newStr

def execute():
	array = []
	for val in frappe.db.sql("""SELECT name,doc_type,value FROM `tabProperty Setter` WHERE name LIKE '%search_fields%'"""):
		print(" ")
		print(val[2])
		mStr = Replace_String(val[2])
		print(mStr)
		print(" ")
		sqlQuery = """UPDATE `tabProperty Setter` SET value = '%s' WHERE name = '%s' AND doc_type = '%s'""" % (mStr,val[0],val[1])
		array.append(sqlQuery)
    
	for x in array:
		sqlQuery2 = x
		frappe.db.sql(x)
		print(x)
		print(" ")
