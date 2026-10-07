# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

# F5: logger replaces the v14 ad-hoc print() statements.
_logger = frappe.logger("fact_frepple", allow_site=True, file_count=1)


class FreppleBuffer(Document):
	pass


# Sync the bin in erpnext with the buffer in frepple
@frappe.whitelist()
def update_frepple_buffer(doc: str) -> None:
	if frappe.get_doc("Frepple Settings").frepple_integration:
		doc = json.loads(doc)
		bin = frappe.get_doc("Bin", doc["name"])  # ERPNext work order

		# Do condition check

		_logger.info(f"{bin}")
		buffers = frappe.db.sql(
			"""
			SELECT item,location,name
			FROM `tabFrepple Buffer`
			WHERE item = %s and location = %s
			""",
			[bin.item_code, bin.warehouse],
			as_dict=1,
		)

		for buffer in buffers:
			frappe.db.set_value(
				"Frepple Buffer",
				buffer.name,
				{
					"onhand": bin.actual_qty,
				},
			)  # Update the quantity
