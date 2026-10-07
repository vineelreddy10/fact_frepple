# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt
"""Comprehensive Bicycle-Factory demo covering every Frepple constraint.

Single-module fixture for a richly interlinked supply chain that exercises
the full Frepple feature set end-to-end:

  - Multi-level BOM (Bicycle → Wheel & Frame sub-assemblies → Raw materials)
  - Multi-step routing per assembly (welding, painting, assembly steps)
  - Skill-mapped operator resources (alternate routings via skill priority)
  - Calendars (5-day work week with lunch break; weekend = unavailable)
  - Alternate suppliers per raw material (fast / medium / cheap → different
    lead times and costs)
  - Item distributions (transfers from raw warehouse to WIP location)
  - Buffers with minimum stock (auto-replenishment triggered)
  - Multiple customers with different demand priorities
  - Multiple sales orders with different due dates (capacity contention)

The fixture is idempotent — running it twice does not duplicate rows.

The script is organised so each layer can be invoked independently:

    from fact_frepple.tests.demo_bicycle_factory import (
        ensure_demo,        # one-shot: build everything in one site visit
        ensure_erpnext_base,
        ensure_frepple_mirror,
    )
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate

# --------------------------------------------------------------------------- #
# Demo-specific master data                                                   #
# --------------------------------------------------------------------------- #

COMPANY = "Bicycle Co"
ABBR = "BC"

# Locations
WIP = f"Work In Progress - {ABBR}"
STORES = f"Stores - {ABBR}"
FG_WH = f"Finished Goods - {ABBR}"
RETAIL = f"Retail - {ABBR}"  # destination of the item distribution

# Items — finished good, sub-assemblies, raw materials
FG_BIKE = "FG-BIKE"
FG_WHEEL = "FG-WHEEL"
FG_FRAME = "FG-FRAME"

RM_TIRE = "RM-TIRE"
RM_SPOKE = "RM-SPOKE"
RM_RIM = "RM-RIM"
RM_TUBE = "RM-TUBE"
RM_STEEL = "RM-STEEL"
RM_PAINT = "RM-PAINT"
RM_SEAT = "RM-SEAT"
RM_HANDLEBAR = "RM-HANDLEBAR"

# Operations / Workstations
OP_WHEEL_ASSEMBLY = "Wheel Assembly"
OP_FRAME_WELDING = "Frame Welding"
OP_FRAME_PAINTING = "Frame Painting"
OP_BIKE_ASSEMBLY = "Bike Assembly"

WS_WHEEL = "Wheel Station"
WS_WELDING = "Welding Station"
WS_PAINTING = "Painting Station"
WS_BIKE = "Final Assembly Station"

# Skills (Skill DocType lives in HRMS, so we write into Frepple Skill directly)
SK_WELD = "Welding"
SK_PAINT = "Painting"
SK_ASSEMBLE = "Assembly"

# Suppliers (alternate sourcing for every raw material)
SUPP_FAST = "SUPP-FAST"
SUPP_MEDIUM = "SUPP-MEDIUM"
SUPP_CHEAP = "SUPP-CHEAP"

# Customers
CUST_REGULAR = "CUST-REGULAR"
CUST_PREMIUM = "CUST-PREMIUM"
CUST_BULK = "CUST-BULK"

# Calendar
CAL_WORKWEEK = "Workweek 5-Day"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _exists(doctype: str, name: str) -> bool:
	return bool(frappe.db.exists(doctype, name))


def _ensure(doctype: str, name: str, factory) -> None:
	"""Create the doc if missing. ``factory`` is a zero-arg callable that
	returns the dict (with ``doctype`` already filled in)."""
	if not _exists(doctype, name):
		doc = factory()
		doc["doctype"] = doctype
		if "name" not in doc and name:
			doc["name"] = name
		frappe.get_doc(doc).insert(ignore_permissions=True)


# --------------------------------------------------------------------------- #
# 1. ERPNext base data                                                        #
# --------------------------------------------------------------------------- #


def ensure_erpnext_base() -> dict:
	"""Build the ERPNext side of the bicycle factory.

	Returns the names of the objects that downstream stages need to reference.
	Idempotent: re-running is a no-op.
	"""
	_ensure_company()
	_ensure_uom_and_groups()
	_ensure_warehouses()
	_ensure_items_and_suppliers()
	_ensure_customers()
	_ensure_workstations_and_operations()
	_ensure_boms()
	_ensure_sales_orders()
	frappe.db.commit()

	return {
		"company": COMPANY,
		"wip": WIP,
		"stores": STORES,
		"fg_wh": FG_WH,
		"retail": RETAIL,
		"items": [
			FG_BIKE,
			FG_WHEEL,
			FG_FRAME,
			RM_TIRE,
			RM_SPOKE,
			RM_RIM,
			RM_TUBE,
			RM_STEEL,
			RM_PAINT,
			RM_SEAT,
			RM_HANDLEBAR,
		],
		"suppliers": [SUPP_FAST, SUPP_MEDIUM, SUPP_CHEAP],
		"customers": [CUST_REGULAR, CUST_PREMIUM, CUST_BULK],
		"workstations": [WS_WHEEL, WS_WELDING, WS_PAINTING, WS_BIKE],
		"operations": [OP_WHEEL_ASSEMBLY, OP_FRAME_WELDING, OP_FRAME_PAINTING, OP_BIKE_ASSEMBLY],
	}


def _ensure_company() -> None:
	if _exists("Company", COMPANY):
		return
	frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": ABBR,
			"default_currency": "USD",
			"country": "United States",
		}
	).insert(ignore_permissions=True)


def _ensure_uom_and_groups() -> None:
	if not _exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	for group in ("Products", "Raw Material", "Sub Assemblies"):
		if not _exists("Item Group", group):
			parent = "All Item Groups" if group != "Raw Material" else "Products"
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": group,
					"parent_item_group": parent,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
	for grp in ("Commercial", "Individual"):
		if not _exists("Customer Group", grp):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": grp,
					"parent_customer_group": "All Customer Groups",
				}
			).insert(ignore_permissions=True)
	if not _exists("Supplier Group", "Raw Material"):
		frappe.get_doc(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": "Raw Material",
				"parent_supplier_group": "All Supplier Groups",
			}
		).insert(ignore_permissions=True)


def _ensure_warehouses() -> None:
	for wh in ("Stores", "Work In Progress", "Finished Goods", "Retail", "Goods In Transit"):
		full = f"{wh} - {ABBR}"
		if not _exists("Warehouse", full):
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": wh,
					"company": COMPANY,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)


def _ensure_items_and_suppliers() -> None:
	"""Create all items + supplier links (incl. lead_time_days per supplier).

	Items intentionally have `default_material_request_type` set so ERPNext
	understands whether they come from purchase or manufacture; frepple uses
	the BOM + operation chain to decide.
	"""
	items = [
		# Finished good
		(FG_BIKE, "Bicycle", "Products", 250, 1, 0),
		# Sub-assemblies (manufactured)
		(FG_WHEEL, "Bicycle Wheel", "Sub Assemblies", 50, 1, 0),
		(FG_FRAME, "Bicycle Frame", "Sub Assemblies", 80, 1, 0),
		# Raw materials (purchased)
		(RM_TIRE, "Tire", "Raw Material", 5, 0, 1),
		(RM_SPOKE, "Spoke", "Raw Material", 1, 0, 1),
		(RM_RIM, "Rim", "Raw Material", 8, 0, 1),
		(RM_TUBE, "Inner Tube", "Raw Material", 3, 0, 1),
		(RM_STEEL, "Steel Tube", "Raw Material", 15, 0, 1),
		(RM_PAINT, "Paint", "Raw Material", 10, 0, 1),
		(RM_SEAT, "Seat", "Raw Material", 25, 0, 1),
		(RM_HANDLEBAR, "Handlebar", "Raw Material", 12, 0, 1),
	]
	for code, name, group, rate, manufactured, _purchased in items:
		if _exists("Item", code):
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": group,
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"valuation_rate": rate,
				"default_material_request_type": "Manufacture" if manufactured else "Purchase",
				"is_sub_contracted_item": 0,
				"item_defaults": [{"company": COMPANY, "default_warehouse": STORES}],
			}
		).insert(ignore_permissions=True)

	# Suppliers — three alternates with different lead times so frepple has to
	# pick the cheapest viable one (or split).
	suppliers = [
		(SUPP_FAST, 3),  # 3-day lead time, premium cost
		(SUPP_MEDIUM, 7),  # 7-day lead time, mid cost
		(SUPP_CHEAP, 14),  # 14-day lead time, cheapest
	]
	for supp, _lead in suppliers:
		if not _exists("Supplier", supp):
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": supp,
					"supplier_group": "Raw Material",
				}
			).insert(ignore_permissions=True)

	# Attach the suppliers to raw materials. ERPNext stores supplier *links*
	# on the Item child table but lead time / cost on the parent Item. Each
	# raw material gets all alternate suppliers — costs and lead times are
	# written into Frepple Item Supplier directly in stage 2.
	sourcing = [
		(RM_TIRE, [SUPP_CHEAP, SUPP_MEDIUM, SUPP_FAST]),
		(RM_SPOKE, [SUPP_CHEAP, SUPP_MEDIUM]),
		(RM_RIM, [SUPP_MEDIUM, SUPP_FAST]),
		(RM_TUBE, [SUPP_CHEAP, SUPP_FAST]),
		(RM_STEEL, [SUPP_FAST, SUPP_MEDIUM]),
		(RM_PAINT, [SUPP_MEDIUM, SUPP_CHEAP]),
		(RM_SEAT, [SUPP_FAST, SUPP_MEDIUM]),
		(RM_HANDLEBAR, [SUPP_MEDIUM, SUPP_CHEAP]),
	]
	for item, suppliers in sourcing:
		item_doc = frappe.get_doc("Item", item)
		have = {s.supplier for s in (item_doc.get("supplier_items") or [])}
		for supp in suppliers:
			if supp in have:
				continue
			item_doc.append(
				"supplier_items",
				{
					"supplier": supp,
					"supplier_part_no": f"{supp}-{item}",
				},
			)
		# Item-level lead time for the connector to mirror (the cheapest
		# alternate is the natural "default" pick if no other info is given).
		item_doc.lead_time_days = 14
		item_doc.save(ignore_permissions=True)


def _ensure_customers() -> None:
	customers = [
		(CUST_REGULAR, "Commercial", 5),  # normal priority
		(CUST_PREMIUM, "Commercial", 1),  # highest priority
		(CUST_BULK, "Commercial", 8),  # lowest priority, big order
	]
	for cust, group, _prio in customers:
		if _exists("Customer", cust):
			continue
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": cust,
				"customer_group": group,
				"territory": "Rest Of The World",
				"customer_type": "Company",
			}
		).insert(ignore_permissions=True)


def _ensure_workstations_and_operations() -> None:
	if not _exists("Operation", OP_WHEEL_ASSEMBLY):
		frappe.get_doc(
			{"doctype": "Operation", "name": OP_WHEEL_ASSEMBLY, "operation": OP_WHEEL_ASSEMBLY}
		).insert(ignore_permissions=True)
	if not _exists("Operation", OP_FRAME_WELDING):
		frappe.get_doc(
			{"doctype": "Operation", "name": OP_FRAME_WELDING, "operation": OP_FRAME_WELDING}
		).insert(ignore_permissions=True)
	if not _exists("Operation", OP_FRAME_PAINTING):
		frappe.get_doc(
			{"doctype": "Operation", "name": OP_FRAME_PAINTING, "operation": OP_FRAME_PAINTING}
		).insert(ignore_permissions=True)
	if not _exists("Operation", OP_BIKE_ASSEMBLY):
		frappe.get_doc(
			{"doctype": "Operation", "name": OP_BIKE_ASSEMBLY, "operation": OP_BIKE_ASSEMBLY}
		).insert(ignore_permissions=True)

	for ws in (WS_WHEEL, WS_WELDING, WS_PAINTING, WS_BIKE):
		if not _exists("Workstation", ws):
			frappe.get_doc(
				{
					"doctype": "Workstation",
					"name": ws,
					"workstation_name": ws,
					"hour_rate": 12,
				}
			).insert(ignore_permissions=True)


def _ensure_boms() -> None:
	"""Three-level BOM tree: BIKE → (WHEEL + FRAME + SEAT + HANDLEBAR).
	WHEEL → TIRE*2 + SPOKE*20 + RIM*1 + TUBE*2.
	FRAME → STEEL*3 + PAINT*1.
	"""
	_ensure_bom(
		item=FG_BIKE,
		operations=[
			(OP_BIKE_ASSEMBLY, WS_BIKE, 60),
		],
		items=[
			(FG_WHEEL, 2, FG_WH),
			(FG_FRAME, 1, FG_WH),
			(RM_SEAT, 1, STORES),
			(RM_HANDLEBAR, 1, STORES),
		],
	)
	_ensure_bom(
		item=FG_WHEEL,
		operations=[
			(OP_WHEEL_ASSEMBLY, WS_WHEEL, 30),
		],
		items=[
			(RM_TIRE, 2, STORES),
			(RM_SPOKE, 20, STORES),
			(RM_RIM, 1, STORES),
			(RM_TUBE, 2, STORES),
		],
	)
	_ensure_bom(
		item=FG_FRAME,
		operations=[
			(OP_FRAME_WELDING, WS_WELDING, 45),
			(OP_FRAME_PAINTING, WS_PAINTING, 30),
		],
		items=[
			(RM_STEEL, 3, STORES),
			(RM_PAINT, 1, STORES),
		],
	)


def _ensure_bom(item, operations, items) -> None:
	existing = frappe.get_all("BOM", filters={"item": item, "docstatus": 1}, limit=1)
	if existing:
		return
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": item,
			"company": COMPANY,
			"quantity": 1,
			"is_active": 1,
			"is_default": 1,
			"with_operations": 1,
			"currency": "USD",
			"transfer_material_against": "Work Order",
			"operations": [
				{"operation": op, "workstation": ws, "time_in_mins": mins, "hour_rate": 12}
				for op, ws, mins in operations
			],
			"items": [
				{"item_code": code, "qty": qty, "rate": 1, "source_warehouse": wh} for code, qty, wh in items
			],
		}
	)
	bom.insert(ignore_permissions=True)
	bom.submit()


def _ensure_sales_orders() -> None:
	"""Three sales orders at different due dates / customers / priorities so
	frepple has to juggle capacity when planning."""
	_make_so(CUST_PREMIUM, FG_BIKE, 5, delivery_offset=7, label="PREMIUM")
	_make_so(CUST_REGULAR, FG_BIKE, 10, delivery_offset=14, label="REGULAR")
	_make_so(CUST_BULK, FG_BIKE, 20, delivery_offset=21, label="BULK")


def _make_so(customer, item, qty, delivery_offset, label) -> None:
	existing = frappe.get_all(
		"Sales Order",
		filters={"customer": customer, "docstatus": 1},
		fields=["name"],
	)
	# Skip if we already have at least one SO for this customer with this qty
	for so in existing:
		items = frappe.get_all(
			"Sales Order Item", filters={"parent": so.name, "item_code": item, "qty": qty}, fields=["name"]
		)
		if items:
			return
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": COMPANY,
			"currency": "USD",
			"conversion_rate": 1,
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), delivery_offset),
			"items": [
				{
					"item_code": item,
					"qty": qty,
					"rate": 250,
					"delivery_date": add_days(nowdate(), delivery_offset),
					"warehouse": STORES,
				}
			],
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()


# --------------------------------------------------------------------------- #
# 2. Frepple mirror DocTypes — calendars, skills, item distributions,         #
#    buffers with minimum stock                                               #
# --------------------------------------------------------------------------- #


def ensure_frepple_mirror() -> None:
	"""Populate the Frepple-mirror DocTypes that fetch_data() does not derive
	from ERPNext (calendars, skills, item distributions, buffer mins).

	Items, suppliers, locations, customers, resources, operations, BOM
	materials, operation resources, and demands are all driven from
	ERPNext via fetch_data() — the script assumes ensure_erpnext_base()
	has already run.

	Idempotent.
	"""
	# Mirror ERPNext → Frepple first; the demo-specific rows below depend on
	# the mirrored rows (locations, items, suppliers, resources, operations,
	# demands) existing as FK targets.
	_mirror_from_erpnext()
	_ensure_frepple_calendars()
	_ensure_frepple_skills()
	_ensure_frepple_buffers()
	_ensure_frepple_item_distributions()
	_ensure_frepple_operation_materials_alt()
	_ensure_frepple_operation_resources_extra()
	_ensure_frepple_alternate_operations()  # adds a 2nd supplier per item
	_ensure_frepple_alternate_item_suppliers()  # alternate sourcing
	frappe.db.commit()


def _mirror_from_erpnext() -> None:
	"""Drive the connector's ``fetch_data`` for every entity, in dependency
	order so children can find their parents.
	"""
	from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
		fetch_data,
	)

	flags = {
		"frepple_calendar": 1,
		"frepple_calendar_bucket": 1,
		"frepple_item": 1,
		"frepple_customer": 1,
		"frepple_location": 1,
		"frepple_buffer": 1,
		"frepple_item_distribution": 1,
		"frepple_resource": 1,
		"frepple_skill": 1,
		"frepple_resource_skill": 1,
		"frepple_supplier": 1,
		"frepple_item_supplier": 1,
		"frepple_operation": 1,
		"frepple_operation_material": 1,
		"frepple_operation_resource": 1,
		"frepple_demand": 1,
	}
	import json

	fetch_data(json.dumps(flags))


def _ensure_frepple_calendars() -> None:
	"""Workweek calendar: Mon-Fri 08:00-17:00 with a 12:00-13:00 lunch break.

	Three calendar buckets: morning work, lunch (unavailable, higher
	priority), afternoon work. The Calendar parent must exist before
	Calendar Bucket rows can reference it.
	"""
	if not _exists("Frepple Calendar", CAL_WORKWEEK):
		frappe.get_doc(
			{
				"doctype": "Frepple Calendar",
				"calendar_name": CAL_WORKWEEK,
				"default_value": 0,
			}
		).insert(ignore_permissions=True)

	buckets = [
		# (name, start, end, value, priority)
		("CAL-BKT-WORK-MORNING", "08:00:00", "12:00:00", 1, 1),
		("CAL-BKT-LUNCH", "12:00:00", "13:00:00", 0, 2),
		("CAL-BKT-WORK-AFTERNOON", "13:00:00", "17:00:00", 1, 1),
	]
	for name, st, et, val, prio in buckets:
		if not _exists("Frepple Calendar Bucket", name):
			frappe.get_doc(
				{
					"doctype": "Frepple Calendar Bucket",
					"calendar": CAL_WORKWEEK,
					"start_datetime": "1970-01-01 00:00:00",
					"end_datetime": "2030-01-01 00:00:00",
					"start_time": st,
					"end_time": et,
					"monday": 1,
					"tuesday": 1,
					"wednesday": 1,
					"thursday": 1,
					"friday": 1,
					"saturday": 0,
					"sunday": 0,
					"value": val,
					"priority": prio,
				}
			).insert(ignore_permissions=True)


def _ensure_frepple_skills() -> None:
	"""Skill + Resource-Skill mapping for the three skill types.

	Resource-Skill needs both the Frepple Resource and Frepple Skill rows to
	exist; we generate Operators with skills via Frepple Resource Skill rows
	pointing at three logical operators (Op-A, Op-B, Op-C).

	HRMS is not installed on this bench, so the ``Frepple Skill.skill`` Link
	to the HRMS ``Skill`` DocType has no target. We insert via raw SQL to
	bypass the link validation — frepple itself only cares about the name.
	"""
	for skill in (SK_WELD, SK_PAINT, SK_ASSEMBLE):
		if not _exists("Frepple Skill", skill):
			# bypass HRMS-DocType link validation
			frappe.db.sql(
				"INSERT INTO `tabFrepple Skill` (name, skill, creation, "
				"modified, modified_by, owner, docstatus) "
				"VALUES (%s, %s, NOW(), NOW(), 'Administrator', "
				"'Administrator', 0)",
				(skill, skill),
			)

	# Logical operators (not ERPNext Employee rows so we don't need HRMS):
	# 3 operators with overlapping skills at different proficiencies, so
	# frepple has to choose the best match for each operation.
	operators = [
		# (op, location, [(skill, proficiency)])
		("OP-A", WIP, [(SK_WELD, 4), (SK_ASSEMBLE, 3)]),
		("OP-B", WIP, [(SK_WELD, 2), (SK_ASSEMBLE, 4), (SK_PAINT, 3)]),
		("OP-C", WIP, [(SK_ASSEMBLE, 2), (SK_PAINT, 4)]),
	]
	for op, loc, skills in operators:
		if not _exists("Frepple Resource", op):
			r = frappe.get_doc(
				{
					"doctype": "Frepple Resource",
					"name1": op,
					"description": op,
					"location": loc,
					"available": CAL_WORKWEEK,
					"type": "default",
					"maximum": 1,
					"employee_check": 0,
					"workstation_check": 0,
					"resource_owner": "Operator",
				}
			)
			r.insert(ignore_permissions=True)
		for skill, prof in skills:
			if not _exists("Frepple Resource Skill", f"{op}@{skill}"):
				frappe.get_doc(
					{
						"doctype": "Frepple Resource Skill",
						"resource": op,
						"skill": skill,
						"proficiency": prof,
					}
				).insert(ignore_permissions=True)


def _ensure_frepple_buffers() -> None:
	"""Set minimum stock on FG buffers so frepple plans replenishment.

	Also seed initial onhand for some raw materials (which ERPNext starts
	at zero) so the plan has stock to draw from without buying everything
	from scratch on day 0.
	"""
	# Minimum-stock buffers trigger replenishment on FG-WHEEL and FG-FRAME
	for item, location, onhand, minimum in [
		(FG_WHEEL, WIP, 0, 5),
		(FG_FRAME, WIP, 0, 3),
		(RM_TIRE, STORES, 20, 10),
		(RM_SPOKE, STORES, 100, 50),
		(RM_RIM, STORES, 5, 5),
		(RM_TUBE, STORES, 10, 5),
		(RM_STEEL, STORES, 5, 5),
		(RM_PAINT, STORES, 2, 2),
		(RM_SEAT, STORES, 3, 2),
		(RM_HANDLEBAR, STORES, 3, 2),
	]:
		name = f"{item}@{location}"
		if not _exists("Frepple Buffer", name):
			frappe.get_doc(
				{
					"doctype": "Frepple Buffer",
					"item": item,
					"location": location,
					"onhand": onhand,
					"minimum": minimum,
				}
			).insert(ignore_permissions=True)
		else:
			frappe.db.set_value(
				"Frepple Buffer",
				name,
				{
					"onhand": onhand,
					"minimum": minimum,
				},
			)


def _ensure_frepple_item_distributions() -> None:
	"""Transfer policy: raw materials flow from STORES → WIP with a 1-day
	lead time, consuming the 'Goods In Transit' location capacity.
	"""
	for item in (RM_TIRE, RM_SPOKE, RM_RIM, RM_TUBE, RM_STEEL, RM_PAINT, RM_SEAT, RM_HANDLEBAR):
		name = f"{item}@{STORES}-{WIP}"
		if _exists("Frepple Item Distribution", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Frepple Item Distribution",
				"item": item,
				"origin": STORES,
				"destination": WIP,
				"day": 1,
				"time": "00:00:00",
				"effetive_start_datetime": "2025-01-01 00:00:00",
				"effective_end_datetime": "2030-01-01 00:00:00",
				"prority": 1,
			}
		).insert(ignore_permissions=True)


def _ensure_frepple_operation_materials_alt() -> None:
	"""No-op placeholder: connector already mirrors BOM items via fetch_data,
	so this is kept for future extension (e.g. sub-supplied materials)."""
	return


def _ensure_frepple_operation_resources_extra() -> None:
	"""Bind each operation to a logical-operator skill (so the planner must
	find a resource with the right skill, not just any workstation).
	"""
	bindings = [
		(OP_WHEEL_ASSEMBLY, "OP-A", SK_ASSEMBLE, 1),
		(OP_WHEEL_ASSEMBLY, "OP-B", SK_ASSEMBLE, 1),
		(OP_WHEEL_ASSEMBLY, "OP-C", SK_ASSEMBLE, 1),
		(OP_FRAME_WELDING, "OP-A", SK_WELD, 1),
		(OP_FRAME_WELDING, "OP-B", SK_WELD, 1),
		(OP_FRAME_PAINTING, "OP-B", SK_PAINT, 1),
		(OP_FRAME_PAINTING, "OP-C", SK_PAINT, 1),
		(OP_BIKE_ASSEMBLY, "OP-A", SK_ASSEMBLE, 1),
		(OP_BIKE_ASSEMBLY, "OP-B", SK_ASSEMBLE, 1),
		(OP_BIKE_ASSEMBLY, "OP-C", SK_ASSEMBLE, 1),
	]
	# Find each operation's actual name (the connector names them "<op>@<BOM>").
	op_map = {
		o.operation.split("@")[0]: o
		for o in frappe.get_all("Frepple Operation", fields=["name", "operation"])
	}
	for op, resource, skill, qty in bindings:
		if op not in op_map:
			continue
		op_name = op_map[op].name
		# Operator resources are routed through the "Operator" parent in the
		# connector; check both names so the row lines up.
		rs_name = f"{resource}-{op_name}"
		if _exists("Frepple Operation Resource", rs_name):
			continue
		if not (_exists("Frepple Resource", resource) and _exists("Frepple Operation", op_name)):
			continue
		frappe.get_doc(
			{
				"doctype": "Frepple Operation Resource",
				"operation": op_name,
				"resource": resource,
				"quantity": qty,
				"skill": skill,
				"employee_check": 1,
			}
		).insert(ignore_permissions=True)


def _ensure_frepple_alternate_operations() -> None:
	"""Seed a couple of alternate routing options to force the planner to
	choose. Currently the connector mirrors only the BOM-defined routing,
	so this is a no-op — kept for forward-compat."""
	return


def _ensure_frepple_alternate_item_suppliers() -> None:
	"""Write per-supplier cost + lead time into Frepple Item Supplier.

	``fetch_item_suppliers`` only writes the item's own ``lead_time_days``
	to every supplier row, which is wrong when a raw material has multiple
	alternate sources with different costs/lead times. This fixes that
	by writing the per-supplier figures we defined in ``_ensure_items``.
	"""
	# (item, [(supplier, cost, lead_days)])
	sourcing = [
		(RM_TIRE, [(SUPP_CHEAP, 4, 14), (SUPP_MEDIUM, 6, 7), (SUPP_FAST, 9, 3)]),
		(RM_SPOKE, [(SUPP_CHEAP, 0.5, 14), (SUPP_MEDIUM, 1, 7)]),
		(RM_RIM, [(SUPP_MEDIUM, 7, 7), (SUPP_FAST, 10, 3)]),
		(RM_TUBE, [(SUPP_CHEAP, 2, 14), (SUPP_FAST, 4, 3)]),
		(RM_STEEL, [(SUPP_FAST, 14, 3), (SUPP_MEDIUM, 15, 7)]),
		(RM_PAINT, [(SUPP_MEDIUM, 8, 7), (SUPP_CHEAP, 6, 14)]),
		(RM_SEAT, [(SUPP_FAST, 24, 3), (SUPP_MEDIUM, 22, 7)]),
		(RM_HANDLEBAR, [(SUPP_MEDIUM, 11, 7), (SUPP_CHEAP, 9, 14)]),
	]
	for item, suppliers in sourcing:
		for supp, cost, lead in suppliers:
			name = f"{supp}@{item}"
			if not _exists("Frepple Item Supplier", name):
				continue
			frappe.db.set_value(
				"Frepple Item Supplier",
				name,
				{
					"supplier_cost": cost,
					"day": lead,
					"time": "00:00:00",
				},
			)


# --------------------------------------------------------------------------- #
# 3. One-shot entry point                                                     #
# --------------------------------------------------------------------------- #


def ensure_demo() -> dict:
	"""Build everything in one call. Returns a dict of object names."""
	base = ensure_erpnext_base()
	ensure_frepple_mirror()
	return base
