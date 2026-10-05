# -*- coding: utf-8 -*-
# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document

from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import so_status_e2f


# F5: logger replaces the v14 ad-hoc print() statements.
_logger = frappe.logger("fact_frepple", allow_site=True, file_count=1)

class FreppleDemand(Document):
	pass

# Sync the status of work order in erpnext with the manufacturing order in frepple
@frappe.whitelist()
def update_frepple_demand_status(doc: str) -> None:
	doc = json.loads(doc)
	if (frappe.get_doc("Frepple Settings").frepple_integration) and doc["docstatus"]:
		erpnext_so = frappe.get_doc("Sales Order",doc["name"]) #ERPNext sales order

		_logger.info(f"{erpnext_so}")
		sos = frappe.db.sql(
			"""
			SELECT name,so_owner
			FROM `tabFrepple Demand`
			WHERE so_owner = %s
			""",
		erpnext_so.name,as_dict=1)

		for so in sos:
			frappe.db.set_value('Frepple Demand', so.name, 'status',so_status_e2f(erpnext_so.status)) #Update the status
			_logger.info(f"{so_status_e2f(erpnext_so.status)}")

