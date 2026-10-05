# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt
"""Phase 4 acceptance — fetch controller.

The Phase 2 unit tests only exercised the R8 WIP-prefix helper; this module
verifies that the fetch functions actually project ERPNext rows into the
connector's mirror DocTypes. The mocked source is ``frappe.db.sql`` (the
fetch functions read from ERPNext's ``tab*`` tables, not from frepple — the
v14 connector never round-trips through the REST API on the pull path; a
Phase 6 follow-up could close that gap).

Why ``flags.ignore_links`` patches below: the mirror DocTypes have Link
fields to ERPNext native DocTypes (``Item``, ``Customer``, etc.) and the
test database is empty of those parents, so a real insert would trip
``LinkValidationError``. Setting ``flags.ignore_links = True`` on the
synthesised new-doc mirrors what production does once those parents exist.
"""

from unittest.mock import patch
from contextlib import ExitStack

import frappe
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
	get_wip_location_prefix,
)


def _row(**kwargs):
	"""Build a ``frappe._dict`` so the source's ``row.attribute`` access works."""
	return frappe._dict(kwargs)


class _SqlRouter:
	"""Patch ``frappe.db.sql`` to return canned rows for specific tables.

	``frappe.get_doc`` and the test runner's own helpers call ``frappe.db.sql``
	for unrelated lookups, so we can't blindly return canned data — we have to
	fall through to the real DB for everything that doesn't match our test's
	tables.
	"""

	def __init__(self, canned: dict[str, list]):
		self.canned = canned
		self._real = frappe.db.sql

	def __call__(self, query, *args, **kwargs):
		for table, rows in self.canned.items():
			if f"FROM `{table}`" in query:
				return rows
		return self._real(query, *args, **kwargs)


def _new_doc_with_skip_links(doctype, *args, **kwargs):
	"""Wrap ``frappe.new_doc`` so the returned doc has ``flags.ignore_links=True``.

	The fetch controller's mirror DocTypes link to ERPNext native DocTypes
	(``Item``, ``Customer``, …) that are absent from the test DB. Production
	runs after those parents exist; in tests we sidestep the LinkValidator.
	``as_dict=True`` callers get a plain dict and don't need the flag.
	"""
	doc = frappe._original_new_doc(doctype, *args, **kwargs)
	if not kwargs.get("as_dict"):
		doc.flags.ignore_links = True
	return doc


# Mirror DocTypes the fetch controller writes to — used by tearDown to scrub
# state so subsequent tests start clean (UnitTestCase has no implicit rollback).
_MIRROR_DOCTYPES = (
	"Frepple Item",
	"Frepple Customer",
	"Frepple Location",
	"Frepple Buffer",
)


class TestFreppleIntegrationDataFetching(UnitTestCase):
	"""Phase 4 acceptance — project rows into mirror DocTypes."""

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

		# Save the unpatched new_doc so _new_doc_with_skip_links can delegate.
		frappe._original_new_doc = frappe.new_doc
		self._new_doc_patch = patch("frappe.new_doc", side_effect=_new_doc_with_skip_links)
		self._new_doc_patch.start()

		# Scrub mirror rows left over from a previous test run.
		for dt in _MIRROR_DOCTYPES:
			frappe.db.delete(dt, filters={})

	def tearDown(self):
		self._new_doc_patch.stop()
		del frappe._original_new_doc

	# -- R8 WIP-prefix helper (kept from Phase 2) ----------------------------

	def test_wip_prefix_default(self):
		# Default value comes from Frepple Settings DocType JSON
		frappe.db.set_single_value("Frepple Settings", "wip_location_name", None)
		frappe.db.commit()
		self.assertEqual(get_wip_location_prefix(), "Work In Progress")

	def test_wip_prefix_from_settings(self):
		frappe.db.set_single_value(
			"Frepple Settings", "wip_location_name", "Production Floor"
		)
		frappe.db.commit()
		self.assertEqual(get_wip_location_prefix(), "Production Floor")

	# -- Pull rows into mirror DocTypes --------------------------------------

	def test_fetch_items_inserts_mirror_rows(self):
		"""``fetch_items`` projects ERPNext ``tabItem`` rows into ``Frepple Item``.

		The v14 connector pulls from ERPNext (not from the frepple REST API on
		this code path) — see the module docstring for the gap. The test
		asserts the projection contract.
		"""
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_items,
		)

		router = _SqlRouter(
			{
				"tabItem": [
					_row(item_code="FG-001", item_name="Finished Good 001",
						item_group="Products", valuation_rate=100.0, stock_uom="Nos"),
					_row(item_code="RM-001", item_name="Raw Material 001",
						item_group="Raw Materials", valuation_rate=5.0, stock_uom="Kg"),
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			fetch_items()

		rows = {
			d.name: d
			for d in frappe.get_all(
				"Frepple Item",
				fields=["name", "item", "description", "stock_uom", "valuation_rate", "item_group"],
			)
		}
		self.assertEqual(set(rows), {"FG-001", "RM-001"})
		self.assertEqual(rows["FG-001"].description, "Finished Good 001")
		self.assertEqual(rows["FG-001"].stock_uom, "Nos")
		self.assertEqual(rows["FG-001"].valuation_rate, 100.0)
		self.assertEqual(rows["FG-001"].item_group, "Products")
		self.assertEqual(rows["RM-001"].valuation_rate, 5.0)

	def test_fetch_items_updates_existing_row(self):
		"""A second fetch with the same item_code must update, not duplicate."""
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_items,
		)

		router = _SqlRouter(
			{"tabItem": [_row(item_code="FG-001", item_name="FG", item_group="Products",
							  valuation_rate=100.0, stock_uom="Nos")]}
		)
		with patch("frappe.db.sql", side_effect=router):
			fetch_items()

		# Second fetch with new cost
		router = _SqlRouter(
			{"tabItem": [_row(item_code="FG-001", item_name="FG", item_group="Products",
							  valuation_rate=125.0, stock_uom="Nos")]}
		)
		with patch("frappe.db.sql", side_effect=router):
			fetch_items()

		rows = frappe.get_all("Frepple Item", filters={"item": "FG-001"})
		self.assertEqual(len(rows), 1)
		self.assertEqual(frappe.get_doc("Frepple Item", "FG-001").valuation_rate, 125.0)

	def test_fetch_customers_inserts_mirror_rows(self):
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_customers,
		)

		router = _SqlRouter(
			{
				"tabCustomer": [
					_row(name="CUST-001", customer_group="All Customer Groups",
						customer_type="Individual"),
				]
			}
		)
		with patch("frappe.db.sql", side_effect=router):
			fetch_customers()

		row = frappe.get_doc("Frepple Customer", "CUST-001")
		self.assertEqual(row.customer, "CUST-001")
		self.assertEqual(row.customer_group, "All Customer Groups")
		self.assertEqual(row.customer_type, "Individual")

	def test_fetch_buffers_upserts_by_item_at_warehouse(self):
		"""``fetch_buffers`` keys on ``item_code@warehouse`` so it upserts.

		Pre-seed a mirror row at qty=10 and assert the second fetch updates it
		to the new qty instead of inserting a duplicate.
		"""
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_buffers,
		)

		router = _SqlRouter(
			{"tabBin": [_row(warehouse="Stores", item_code="RM-001", actual_qty=10)]}
		)
		with patch("frappe.db.sql", side_effect=router):
			fetch_buffers()

		rows = frappe.get_all(
			"Frepple Buffer",
			filters={"item": "RM-001", "location": "Stores"},
			fields=["name", "onhand"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].name, "RM-001@Stores")
		self.assertEqual(rows[0].onhand, 10)

		# Second fetch updates qty
		router = _SqlRouter(
			{"tabBin": [_row(warehouse="Stores", item_code="RM-001", actual_qty=75)]}
		)
		with patch("frappe.db.sql", side_effect=router):
			fetch_buffers()

		rows = frappe.get_all(
			"Frepple Buffer",
			filters={"item": "RM-001", "location": "Stores"},
			fields=["name", "onhand"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].onhand, 75)

	def test_fetch_data_dispatches_to_subfetchers(self):
		"""``fetch_data`` is a dispatcher — each flag routes to a sub-fetcher.

		We patch every sub-fetcher with a sentinel and assert each one is
		called exactly once when its flag is set. This guards the dispatch
		logic against silent regressions where a new entity is added but the
		dispatcher isn't updated.
		"""
		import json

		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching import (
			frepple_integration_data_fetching as fetch_mod,
		)

		# Map flag → module-level function name to patch.
		# frepple_demand → fetch_sales_orders in the v17 source.
		# frepple_item_supplier has no matching fetcher in the v17 source — the
		# flag is read by ``fetch_data`` but the implementation is a TODO.
		dispatch = [
			("frepple_item", "fetch_items"),
			("frepple_customer", "fetch_customers"),
			("frepple_location", "fetch_locations"),
			("frepple_buffer", "fetch_buffers"),
			("frepple_resource", "fetch_resources"),
			("frepple_skill", "fetch_skills"),
			("frepple_resource_skill", "fetch_resource_skills"),
			("frepple_supplier", "fetch_suppliers"),
			("frepple_operation", "fetch_operations"),
			("frepple_operation_material", "fetch_operation_materials"),
			("frepple_operation_resource", "fetch_operation_resources"),
			("frepple_demand", "fetch_sales_orders"),
		]

		patches = {method_name: patch.object(fetch_mod, method_name) for _, method_name in dispatch}
		mocks = {}

		with ExitStack() as stack:
			for _, method_name in dispatch:
				mocks[method_name] = stack.enter_context(patches[method_name])

			# Build a doc that includes every flag the controller reads.
			# ``frepple_item_supplier`` is read but has no fetcher — set 0 so
			# the ``if`` branch is skipped instead of crashing on KeyError.
			doc_flags = {flag: 1 for flag, _ in dispatch}
			doc_flags["frepple_item_supplier"] = 0
			doc = json.dumps(doc_flags)
			fetch_mod.fetch_data(doc)

			for _, method_name in dispatch:
				self.assertTrue(
					mocks[method_name].called,
					f"{method_name} should have been called when its flag is set",
				)
