# -*- coding: utf-8 -*-
# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document

class FreppleCalendar(Document):
	pass

@frappe.whitelist()
def fetch_available_2_resource(source_name: str, target_doc: str | None = None) -> str | None:

	doc = json.loads(target_doc)

	# doc = frappe.get_doc("Frepple Resource", source_name)
	frappe.db.set_value('Frepple Resource', source_name, {
		'available': doc["name"],
	})

	return target_doc

@frappe.whitelist()
def fetch_available_2_location(source_name: str, target_doc: str | None = None) -> str | None:

	doc = json.loads(target_doc)

	# doc = frappe.get_doc("Frepple Resource", source_name)
	frappe.db.set_value('Frepple Location', source_name, {
		'available': doc["name"],
	})

	return target_doc