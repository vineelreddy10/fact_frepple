# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt
"""Phase 6 — ERPNext fixtures for the end-to-end two-way transfer test.

Creates the minimal supply chain described in ``specs/migrate-v17.md`` §6.1:
one Sales Order for a manufactured item whose BOM pulls two raw materials,
one of which has a supplier with a lead time. That is the smallest shape that
makes frepple plan *both* a manufacturing order and a purchase order, which is
what the E2E asserts on the way back.

Everything here is idempotent — re-running against a dirty site is a no-op
rather than an error, because the E2E is meant to be runnable repeatedly
against a long-lived dev bench.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate

COMPANY = "Test Co"
ABBR = "TC"
FG = "FG-001"
RM1 = "RM-001"
RM2 = "RM-002"
SUPPLIER = "SUPP-001"
CUSTOMER = "CUST-001"
STORES = f"Stores - {ABBR}"
WIP = f"Work In Progress - {ABBR}"
WORKSTATION = "Assembly Station"
OPERATION = "Assembly"


def _exists(doctype: str, name: str) -> bool:
	return bool(frappe.db.exists(doctype, name))


def ensure_company() -> str:
	if not _exists("Company", COMPANY):
		frappe.get_doc({
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": ABBR,
			"default_currency": "USD",
			"country": "United States",
		}).insert(ignore_permissions=True)
	return COMPANY


def ensure_warehouses() -> None:
	# ERPNext auto-creates Stores/WIP on company insert; only fill the gaps so
	# this stays correct whether or not that behaviour changes.
	for wh in ("Stores", "Work In Progress"):
		full = f"{wh} - {ABBR}"
		if not _exists("Warehouse", full):
			frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": wh,
				"company": COMPANY,
				"is_group": 0,
			}).insert(ignore_permissions=True)


def ensure_uom_and_group() -> None:
	if not _exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	if not _exists("Item Group", "Products"):
		frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": "Products",
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		}).insert(ignore_permissions=True)


def ensure_item(code: str, *, is_manufactured: bool, rate: float) -> str:
	if not _exists("Item", code):
		frappe.get_doc({
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": "Products",
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"valuation_rate": rate,
			"default_material_request_type": "Manufacture" if is_manufactured else "Purchase",
			"item_defaults": [{"company": COMPANY, "default_warehouse": STORES}],
		}).insert(ignore_permissions=True)
	return code


def ensure_supplier() -> str:
	if not _exists("Supplier", SUPPLIER):
		frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": SUPPLIER,
			# Must be a leaf node — ERPNext rejects group nodes like
			# "All Supplier Groups" with a ValidationError.
			"supplier_group": "Raw Material",
		}).insert(ignore_permissions=True)

	# The 7-day lead time is what makes frepple schedule the PO earlier than
	# the MO rather than collapsing both onto the same date.
	item = frappe.get_doc("Item", RM1)
	if not item.get("supplier_items"):
		item.append("supplier_items", {"supplier": SUPPLIER})
		item.lead_time_days = 7
		item.save(ignore_permissions=True)
	return SUPPLIER


def ensure_customer() -> str:
	if not _exists("Customer", CUSTOMER):
		frappe.get_doc({
			"doctype": "Customer",
			"customer_name": CUSTOMER,
			"customer_group": "Commercial",
			"territory": "Rest Of The World",
		}).insert(ignore_permissions=True)
	return CUSTOMER


def ensure_workstation() -> str:
	if not _exists("Operation", OPERATION):
		frappe.get_doc({
			"doctype": "Operation",
			# Operation and Workstation both autoname by prompt, so `name`
			# must be set explicitly rather than derived from the title field.
			"name": OPERATION,
			"operation": OPERATION,
		}).insert(ignore_permissions=True)
	if not _exists("Workstation", WORKSTATION):
		frappe.get_doc({
			"doctype": "Workstation",
			# Workstation autonames by prompt, so `name` must be set explicitly.
			"name": WORKSTATION,
			"workstation_name": WORKSTATION,
			"hour_rate": 10,
		}).insert(ignore_permissions=True)
	return WORKSTATION


def ensure_bom() -> str:
	existing = frappe.get_all("BOM", filters={"item": FG, "docstatus": 1}, limit=1)
	if existing:
		return existing[0].name

	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": FG,
		"company": COMPANY,
		"quantity": 1,
		"is_active": 1,
		"is_default": 1,
		"with_operations": 1,
		"currency": "USD",
		"operations": [{
			"operation": OPERATION,
			"workstation": WORKSTATION,
			"time_in_mins": 30,
			"hour_rate": 10,
		}],
		"items": [
			{"item_code": RM1, "qty": 1, "rate": 10, "source_warehouse": STORES},
			{"item_code": RM2, "qty": 2, "rate": 5, "source_warehouse": STORES},
		],
	})
	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name


def ensure_sales_order() -> str:
	existing = frappe.get_all(
		"Sales Order", filters={"customer": CUSTOMER, "docstatus": 1}, limit=1
	)
	if existing:
		return existing[0].name

	so = frappe.get_doc({
		"doctype": "Sales Order",
		"customer": CUSTOMER,
		"company": COMPANY,
		"currency": "USD",
		"conversion_rate": 1,
		"transaction_date": nowdate(),
		"delivery_date": add_days(nowdate(), 14),
		"items": [{
			"item_code": FG,
			"qty": 10,
			"rate": 100,
			"delivery_date": add_days(nowdate(), 14),
			"warehouse": STORES,
		}],
	})
	so.insert(ignore_permissions=True)
	so.submit()
	return so.name


def create_all() -> dict:
	"""Build the whole fixture set and return the key names."""
	ensure_company()
	ensure_warehouses()
	ensure_uom_and_group()
	ensure_item(FG, is_manufactured=True, rate=100)
	ensure_item(RM1, is_manufactured=False, rate=10)
	ensure_item(RM2, is_manufactured=False, rate=5)
	ensure_supplier()
	ensure_customer()
	ensure_workstation()
	bom = ensure_bom()
	so = ensure_sales_order()
	frappe.db.commit()

	return {"company": COMPANY, "bom": bom, "sales_order": so, "item": FG, "supplier": SUPPLIER}
