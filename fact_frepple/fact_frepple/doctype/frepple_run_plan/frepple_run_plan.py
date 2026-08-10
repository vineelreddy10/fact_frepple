# -*- coding: utf-8 -*-
# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.integrations.utils import make_get_request, make_post_request
from frappe.model.document import Document

from fact_frepple.fact_frepple.doctype.frepple_data_export.frepple_data_export import (
	export_sales_orders,
	get_frepple_params,
)


class FreppleRunPlan(Document):
	pass


# F5: logger replaces the v14 ad-hoc print() statements.
_logger = frappe.logger("fact_frepple", allow_site=True, file_count=1)


@frappe.whitelist()
def run_plan(doc: str) -> dict:
	"""POST to frepple ``/api/runplan/`` and return the raw response.

	The ``constraint``/``plantype``/``env`` query string matches the v9
	``/api/runplan/`` contract (the v14 source used ``/execute/api/runplan/``,
	which doesn't exist on frepple 9.x).
	"""
	doc = json.loads(doc)

	if doc.get("update_frepple"):
		export_sales_orders()
		export_manufacturing_orders()
		export_purchase_orders()

	constraint = 0
	plantype = 1

	if doc.get("constraint"):
		plantype = 1
	if doc.get("unconstraint"):
		plantype = 2
	if doc.get("capacity"):
		constraint = constraint + 4
	if doc.get("lead_time"):
		constraint = constraint + 1
	if doc.get("release_fence"):
		constraint = constraint + 8

	query = f"constraint={constraint}&plantype={plantype}&env=supply"

	settings = frappe.get_doc("Frepple Settings")
	temp_url = settings.url.split("//")
	url = (
		f"http://{settings.username}:{settings.password}@{temp_url[1]}"
		f"/api/runplan/?{query}"
	)
	_logger.info(f"run_plan → {url}")

	headers = {
		"Content-type": "application/json; charset=UTF-8",
		"Authorization": settings.authorization_header,
	}

	output = make_post_request(url, headers=headers, data=None)

	frappe.msgprint(msg="Plan has been run successfully.", title="Success")

	return output


@frappe.whitelist()
def generate_result(doc: str) -> None:
	import_datas = []

	data = import_manufacturing_order()
	import_datas.append("Manufacturing Order Result")
	generate_manufacturing_order(data)

	data = import_purchase_order()
	import_datas.append("Purchase Order Result")
	generate_purchase_order(data)

	for import_data in import_datas:
		frappe.msgprint(_("{0} is imported.").format(import_data))


def export_manufacturing_orders() -> None:
	api = "manufacturingorder"
	url, headers = get_frepple_params(api=api, filter=None)

	mos = frappe.db.sql(
		"""
		SELECT latest_reference, operation, status, quantity
		FROM `tabFrepple Manufacturing Order`
		""",
		as_dict=1,
	)

	for mo in mos:
		_logger.info(f"export_manufacturing_orders row: {mo}")
		data = json.dumps({
			"reference": mo.latest_reference,
			"status": mo.status,
		})
		make_post_request(url, headers=headers, data=data)


def export_purchase_orders() -> None:
	api = "purchaseorder"
	url, headers = get_frepple_params(api=api, filter=None)

	pos = frappe.db.sql(
		"""
		SELECT latest_reference, supplier, status
		FROM `tabFrepple Purchase Order`
		""",
		as_dict=1,
	)

	for po in pos:
		_logger.info(f"export_purchase_orders row: {po}")
		data = json.dumps({
			"reference": po.latest_reference,
			"status": po.status,
		})
		make_post_request(url, headers=headers, data=data)


def import_manufacturing_order() -> list[dict]:
	api = "manufacturingorder"
	filter = "?status=proposed&operation_in=BOM"

	url, headers = get_frepple_params(api=api, filter=filter)
	outputs = make_get_request(url, headers=headers)

	return [output for output in outputs if len(output["operation"].split("@")) == 1]


def generate_manufacturing_order(data: list[dict]) -> None:
	for i in data:
		demands = list(i["plan"]["pegging"].keys())
		for demand in demands:
			mos = frappe.db.sql(
				"""
				SELECT name, demand
				FROM `tabFrepple Manufacturing Order`
				WHERE demand = %s
				""",
				demand,
				as_dict=1,
			)
			_logger.info(f"generate_manufacturing_order candidates: {mos}")

			if not frappe.db.exists("Frepple Manufacturing Order", i["reference"]) and len(mos) == 0:
				new_doc = frappe.new_doc("Frepple Manufacturing Order")
				new_doc.reference = i["reference"]
				new_doc.latest_reference = i["reference"]
				new_doc.operation = i["operation"]
				new_doc.status = i["status"]
				new_doc.quantity = i["quantity"]
				new_doc.completed_quantity = i["quantity_completed"]
				new_doc.start_date = datetime.fromisoformat(i["startdate"])
				new_doc.end_date = datetime.fromisoformat(i["enddate"])
				new_doc.demand = demand
				new_doc.insert()
				_logger.info(f"inserted MO {new_doc.name}")
				continue

			if frappe.db.exists("Frepple Manufacturing Order", i["reference"]) and len(mos) == 0:
				continue

			if frappe.db.exists("Frepple Manufacturing Order", mos[0].name):
				frappe.db.set_value(
					"Frepple Manufacturing Order",
					mos[0].name,
					{
						"latest_reference": i["reference"],
						"operation": i["operation"],
						"status": i["status"],
						"quantity": i["quantity"],
						"start_date": datetime.fromisoformat(i["startdate"]),
						"end_date": datetime.fromisoformat(i["enddate"]),
					},
				)


def import_purchase_order() -> list[dict]:
	api = "purchaseorder"
	filter = "?status=proposed"

	url, headers = get_frepple_params(api=api, filter=filter)
	return make_get_request(url, headers=headers)


def generate_purchase_order(data: list[dict]) -> None:
	for i in data:
		pos = frappe.db.sql(
			"""
			SELECT name, item, supplier
			FROM `tabFrepple Purchase Order`
			WHERE item = %s AND supplier = %s
			""",
			[i["item"], i["supplier"]],
			as_dict=1,
		)
		_logger.info(f"generate_purchase_order candidates: {pos}")

		if len(pos) == 0:
			new_doc = frappe.new_doc("Frepple Purchase Order")
			new_doc.reference = i["reference"]
			new_doc.latest_reference = i["reference"]
			new_doc.supplier = i["supplier"]
			new_doc.status = i["status"]
			new_doc.ordering_date = datetime.fromisoformat(i["startdate"])
			new_doc.receive_date = datetime.fromisoformat(i["enddate"])
			new_doc.item = i["item"]
			new_doc.quantity = i["quantity"]
			new_doc.insert()
			_logger.info(f"inserted PO {new_doc.name}")
		else:
			frappe.db.set_value(
				"Frepple Purchase Order",
				pos[0].name,
				{
					"latest_reference": i["reference"],
					"ordering_date": datetime.fromisoformat(i["startdate"]),
					"receive_date": datetime.fromisoformat(i["enddate"]),
					"quantity": i["quantity"],
				},
			)

