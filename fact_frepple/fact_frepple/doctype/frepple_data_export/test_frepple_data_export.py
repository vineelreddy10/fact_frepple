# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt
"""Phase 4 acceptance — export controller.

Each ``export_<entity>()`` POSTs a JSON payload to frepple's
``/api/input/<entity>/`` endpoint. The Phase 2 unit tests only checked the
URL builder; this module fires real ``requests`` calls through Frappe's
``make_post_request`` and verifies the JSON body that hits the wire. The
``responses`` library mocks frepple at the HTTP-adapter level so no docker
compose / network is needed.
"""

import json
from unittest.mock import patch

import frappe
import responses
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_data_export.frepple_data_export import (
	export_buffers,
	export_calendars,
	export_customers,
	export_items,
	export_locations,
	export_resources,
	export_sales_orders,
	export_skills,
	export_suppliers,
	get_frepple_params,
)


def _captured_post_bodies() -> list[dict]:
	"""Decode every ``responses`` POST body so a test can assert on shape."""
	return [json.loads(call.request.body) for call in responses.calls]


def _basic_auth_url(path: str) -> str:
	"""Build the URL as the connector actually emits it (basic auth in URL).

	``get_frepple_params`` inlines ``user:pass@host`` so frepple's nginx
	basic-auth gate opens without an ``Authorization`` header. We match that
	exact string in ``responses``; otherwise the mismatch surfaces as a
	``ConnectionError`` from the HTTP adapter.
	"""
	return f"http://admin:admin@localhost:9000{path}"


def _row(**kwargs):
	"""Build a dict-like row that supports both ``row["k"]`` and ``row.k``.

	The connector source uses attribute access (``calendar.default_value``);
	``frappe.db.sql(..., as_dict=1)`` returns ``frappe._dict`` which behaves
	that way. Plain ``dict`` doesn't, so we wrap every fixture row here.
	"""
	return frappe._dict(kwargs)


class _SqlRouter:
	"""Patch ``frappe.db.sql`` so we can stub the export's data source while
	letting every other call (controllers, doc-loading, scheduler, etc.) flow
	through to the real implementation.

	The global ``patch("frappe.db.sql", ...)`` is too broad — ``frappe.get_doc``
	internally fires SELECTs that would crash if we returned canned data
	unconditionally. The router inspects the SQL string and only swaps rows
	for tables this test owns; everything else goes to the real DB.
	"""

	def __init__(self, canned: dict[str, list]):
		# table_name → return value (each row already a frappe._dict)
		self.canned = canned
		self._real = frappe.db.sql

	def __call__(self, query, *args, **kwargs):
		for table, rows in self.canned.items():
			if f"FROM `{table}`" in query:
				return rows
		return self._real(query, *args, **kwargs)


class TestFreppleDataExport(UnitTestCase):
	"""Phase 4 acceptance — real JSON-shape coverage per ``export_<entity>()``."""

	def setUp(self):
		frappe.db.set_single_value(
			"Frepple Settings",
			{
				"url": "http://localhost:9000",
				"username": "admin",
				"password": "admin",
				"authorization_header": "",
				"secret_key": "a" * 64,
				"wip_location_name": "Work In Progress",
			},
		)
		frappe.db.commit()

	# -- URL builder (kept from Phase 2) --------------------------------------

	def test_get_frepple_params_builds_basic_auth_url(self):
		url, headers = get_frepple_params(api="item", filter="?limit=10")
		self.assertTrue(url.startswith("http://admin:admin@localhost:9000/api/input/item/"))
		self.assertIn("?limit=10", url)
		self.assertEqual(headers["Content-type"], "application/json; charset=UTF-8")

	def test_get_frepple_params_defaults(self):
		url, _headers = get_frepple_params()
		# empty api/filter fall back to ""
		self.assertTrue(url.endswith("/api/input/") or url.endswith("/api/input//"))

	# -- export_calendars ----------------------------------------------------

	@responses.activate
	def test_export_calendars_posts_calendar_payload(self):
		responses.add(
			responses.POST,
			_basic_auth_url("/api/input/calendar/"),
			status=201,
			json={"pk": 1},
		)

		router = _SqlRouter({"tabFrepple Calendar": [_row(calendar_name="Default", default_value=1.0)]})
		with patch("frappe.db.sql", side_effect=router):
			export_calendars()

		self.assertEqual(len(responses.calls), 1)
		body = _captured_post_bodies()[0]
		self.assertEqual(body, {"name": "Default", "defaultvalue": 1.0})

	# -- export_items --------------------------------------------------------

	@responses.activate
	def test_export_items_posts_group_then_item(self):
		"""``export_items`` first POSTs the item_group as an owner, then the item.

		Two POSTs per row — verified in order so a regression that swaps them
		breaks the test instead of silently succeeding.
		"""
		for _ in range(2):
			responses.add(
				responses.POST,
				_basic_auth_url("/api/input/item/"),
				status=201,
				json={"pk": 1},
			)

		router = _SqlRouter(
			{
				"tabFrepple Item": [
					_row(
						item="FG-001",
						description="Finished Good",
						stock_uom="Nos",
						valuation_rate=100.0,
						item_group="Products",
					)
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			export_items()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 2)
		# First POST = item_group as owner
		self.assertEqual(bodies[0], {"name": "Products"})
		# Second POST = the item itself
		self.assertEqual(
			bodies[1],
			{
				"name": "FG-001",
				"owner": "Products",
				"description": "Finished Good",
				"uom": "Nos",
				"cost": 100.0,
			},
		)

	# -- export_customers ----------------------------------------------------

	@responses.activate
	def test_export_customers_posts_group_then_customer(self):
		for _ in range(2):
			responses.add(
				responses.POST,
				_basic_auth_url("/api/input/customer/"),
				status=201,
				json={"pk": 1},
			)

		router = _SqlRouter(
			{
				"tabFrepple Customer": [
					_row(
						name="CUST-001",
						customer_group="All Customer Groups",
						customer_type="Individual",
					)
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			export_customers()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 2)
		self.assertEqual(bodies[0], {"name": "All Customer Groups"})
		self.assertEqual(
			bodies[1],
			{
				"name": "CUST-001",
				"category": "Individual",
				"owner": "All Customer Groups",
			},
		)

	# -- export_locations ----------------------------------------------------

	@responses.activate
	def test_export_locations_posts_parent_location(self):
		responses.add(
			responses.POST,
			_basic_auth_url("/api/input/location/"),
			status=201,
			json={"pk": 1},
		)

		router = _SqlRouter(
			{"tabFrepple Location": [_row(warehouse="Stores", location_owner=None, available=None)]}
		)
		with patch("frappe.db.sql", side_effect=router):
			export_locations()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 1)
		self.assertEqual(bodies[0], {"name": "Stores", "available": None})

	@responses.activate
	def test_export_locations_posts_child_with_owner(self):
		for _ in range(2):
			responses.add(
				responses.POST,
				_basic_auth_url("/api/input/location/"),
				status=201,
				json={"pk": 1},
			)

		router = _SqlRouter(
			{
				"tabFrepple Location": [
					_row(
						warehouse="Work In Progress - TC",
						location_owner="Test Co",
						available=1,
					)
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			export_locations()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 2)
		self.assertEqual(bodies[0], {"name": "Test Co"})
		self.assertEqual(
			bodies[1],
			{"name": "Work In Progress - TC", "available": 1, "owner": "Test Co"},
		)

	# -- export_buffers ------------------------------------------------------

	@responses.activate
	def test_export_buffers_posts_item_location_onhand(self):
		responses.add(
			responses.POST,
			_basic_auth_url("/api/input/buffer/"),
			status=201,
			json={"pk": 1},
		)

		router = _SqlRouter({"tabFrepple Buffer": [_row(item="RM-001", location="Stores", onhand=50)]})
		with patch("frappe.db.sql", side_effect=router):
			export_buffers()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 1)
		self.assertEqual(
			bodies[0],
			{"item": "RM-001", "location": "Stores", "onhand": 50},
		)

	# -- export_resources ----------------------------------------------------

	@responses.activate
	def test_export_resources_posts_owner_then_resource(self):
		for _ in range(2):
			responses.add(
				responses.POST,
				_basic_auth_url("/api/input/resource/"),
				status=201,
				json={"pk": 1},
			)

		router = _SqlRouter(
			{
				"tabFrepple Resource": [
					_row(
						name1="Operator-001",
						location="Work In Progress - TC",
						available=1,
						type="default",
						maximum=1,
						description="Operator 1",
						resource_owner="Operator",
					)
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			export_resources()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 2)
		self.assertEqual(bodies[0], {"name": "Operator"})
		self.assertEqual(
			bodies[1],
			{
				"name": "Operator-001",
				"available": 1,
				"type": "default",
				"maximum": 1,
				"description": "Operator 1",
				"location": "Work In Progress - TC",
				"owner": "Operator",
			},
		)

	# -- export_skills -------------------------------------------------------

	@responses.activate
	def test_export_skills_posts_skill_name(self):
		responses.add(
			responses.POST,
			_basic_auth_url("/api/input/skill/"),
			status=201,
			json={"pk": 1},
		)

		router = _SqlRouter({"tabFrepple Skill": [_row(skill="Welding")]})
		with patch("frappe.db.sql", side_effect=router):
			export_skills()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 1)
		self.assertEqual(bodies[0], {"name": "Welding"})

	# -- export_suppliers ----------------------------------------------------

	@responses.activate
	def test_export_suppliers_posts_supplier_name(self):
		responses.add(
			responses.POST,
			_basic_auth_url("/api/input/supplier/"),
			status=201,
			json={"pk": 1},
		)

		router = _SqlRouter({"tabFrepple Supplier": [_row(supplier="SUPP-001")]})
		with patch("frappe.db.sql", side_effect=router):
			export_suppliers()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 1)
		self.assertEqual(bodies[0], {"name": "SUPP-001"})

	# -- export_sales_orders -------------------------------------------------

	@responses.activate
	def test_export_sales_orders_posts_demand_payload(self):
		from datetime import datetime

		responses.add(
			responses.POST,
			_basic_auth_url("/api/input/demand/"),
			status=201,
			json={"pk": 1},
		)

		due = datetime(2026, 9, 1, 0, 0, 0)
		router = _SqlRouter(
			{
				"tabFrepple Demand": [
					_row(
						name="SO-001-1",
						item="FG-001",
						item_name="Finished Good 001",
						qty=10,
						location="Stores",
						customer="CUST-001",
						due=due,
						priority=1,
						status="open",
						so_owner="SO-001",
					)
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			export_sales_orders()

		bodies = _captured_post_bodies()
		self.assertEqual(len(bodies), 1)
		body = bodies[0]
		# Static fields check
		self.assertEqual(body["name"], "SO-001-1")
		self.assertEqual(body["item"], "FG-001")
		self.assertEqual(body["customer"], "CUST-001")
		self.assertEqual(body["location"], "Stores")
		self.assertEqual(body["status"], "open")
		self.assertEqual(body["quantity"], 10)
		self.assertEqual(body["priority"], 1)
		# description concatenates item_name + customer
		self.assertIn("Finished Good 001", body["description"])
		self.assertIn("CUST-001", body["description"])
		# due serialised to ISO-8601
		self.assertEqual(body["due"], due.isoformat())
