# -*- coding: utf-8 -*-
# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class FreppleOperationResource(Document):
	pass


@frappe.whitelist()
def add_default_employee() -> str:
	frepple_resource = frappe.db.get_list('Frepple Resource',
		filters={
			'employee_check': 1,
		},
	)
	return frepple_resource[0].name