# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt
from frappe import _


def get_data():
	return [
		{
			"module_name": "Fact Frepple",
			"color": "blue",
			"icon": "fa fa-calendar",
			"type": "module",
			"label": _("Fact Frepple"),
		}
	]
