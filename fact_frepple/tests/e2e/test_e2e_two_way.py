# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt
"""Phase 6 — end-to-end two-way transfer against a *real* frepple container.

Unlike the Phase 4 suite (which mocks HTTP with ``responses``), everything here
talks to the frepple instance configured in ``Frepple Settings``. That is the
whole point: the mocks encode our *belief* about frepple's REST contract, and
only this test can falsify it.

Skipped automatically when frepple is unreachable, so it is safe to leave in
the default test run — a developer without the Docker stack up sees skips, not
failures. Bring the stack up with ``cd docker && sudo make up``.
"""

from __future__ import annotations

import json
import unittest

import frappe
import requests

from fact_frepple.tests.e2e import fixtures
from fact_frepple.tests.e2e.helpers import (
	export_flags,
	fetch_flags,
	frepple_available,
	frepple_settings_configured,
	purge_frepple_input,
	reset_mirror_doctypes,
	reset_work_orders,
)

FREPPLE_ENTITIES_EXPORTED = (
	"item",
	"customer",
	"location",
	"operation",
	"demand",
)


@unittest.skipUnless(frepple_available(), "frepple container not reachable — run `sudo make up`")
class TestE2ETwoWayTransfer(unittest.TestCase):
	"""§6.3 — one Sales Order becomes a frepple plan and comes back as MO + PO."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.settings = frepple_settings_configured()
		cls.fixtures = fixtures.create_all()

	def setUp(self):
		# The mirror DocTypes are the connector's staging area. Clearing them
		# keeps each run independent — without this, the "already exists"
		# branches hide genuine projection failures (the Phase 4 M3 bug).
		reset_mirror_doctypes()
		reset_work_orders()
		purge_frepple_input()

	def test_01_erpnext_is_mirrored_into_connector_doctypes(self):
		"""Step 1 — ``fetch_data`` projects ERPNext rows into mirror DocTypes."""
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_data,
		)

		fetch_data(json.dumps(fetch_flags()))
		frappe.db.commit()

		self.assertTrue(frappe.db.exists("Frepple Item", "FG-001"))
		self.assertTrue(frappe.db.exists("Frepple Item", "RM-001"))
		self.assertTrue(frappe.db.exists("Frepple Customer", "CUST-001"))

		# The demand is the mirrored Sales Order — the thing frepple plans for.
		demands = frappe.get_all(
			"Frepple Demand", filters={"item": "FG-001"}, fields=["name", "qty", "so_owner"]
		)
		self.assertEqual(len(demands), 1, "expected exactly one mirrored demand for FG-001")
		self.assertEqual(demands[0].qty, 10)
		self.assertEqual(demands[0].so_owner, self.fixtures["sales_order"])

	def test_02_export_pushes_entities_to_real_frepple(self):
		"""Step 2 — ``export_data`` POSTs the mirror rows into frepple's REST API."""
		from fact_frepple.fact_frepple.doctype.frepple_data_export.frepple_data_export import (
			export_data,
		)
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_data,
		)

		fetch_data(json.dumps(fetch_flags()))
		frappe.db.commit()

		export_data(json.dumps(export_flags()))

		# Read back through frepple's own API rather than trusting our POSTs.
		items = self._frepple_get("item")
		names = {i["name"] for i in items}
		self.assertIn("FG-001", names)
		self.assertIn("RM-001", names)

		demands = self._frepple_get("demand")
		self.assertTrue(demands, "frepple has no demand after export — nothing to plan")
		exported = [d for d in demands if d["item"] == "FG-001"]
		self.assertEqual(len(exported), 1)
		self.assertEqual(float(exported[0]["quantity"]), 10.0)

	def test_03_run_plan_then_pull_back_mo_and_po(self):
		"""Steps 3-5 — plan in frepple, import the results, generate a Work Order."""
		from fact_frepple.fact_frepple.doctype.frepple_data_export.frepple_data_export import (
			export_data,
		)
		from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
			fetch_data,
		)
		from fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan import (
			generate_result,
			run_plan,
			wait_for_task,
		)

		fetch_data(json.dumps(fetch_flags()))
		frappe.db.commit()
		export_data(json.dumps(export_flags()))

		launched = run_plan(json.dumps({
			"update_frepple": 0,
			"constraint": 1,
			"capacity": 1,
			"lead_time": 1,
			"release_fence": 0,
		}))

		# Planning is asynchronous — reading results before the task finishes
		# returns the previous plan (or nothing), which is how the first E2E
		# run "proved" frepple planned zero manufacturing orders.
		self.assertIn("taskid", launched, f"frepple did not queue a plan task: {launched}")
		status = wait_for_task(launched["taskid"])
		self.assertEqual(status, "Done", f"frepple plan task ended as {status}")

		generate_result(json.dumps({}))
		frappe.db.commit()

		mos = frappe.get_all(
			"Frepple Manufacturing Order",
			filters={"operation": ["like", "%BOM-FG-001%"]},
			fields=["name", "quantity", "demand", "operation", "status"],
		)
		self.assertTrue(mos, "frepple planned no manufacturing order for FG-001")
		self.assertEqual(float(mos[0].quantity), 10.0)

		# Step 5b — the MO becomes a real ERPNext Work Order.
		from fact_frepple.fact_frepple.doctype.frepple_manufacturing_order.frepple_manufacturing_order import (
			generate_erp_wo_bulk,
		)

		generate_erp_wo_bulk(json.dumps([mos[0].name]))
		frappe.db.commit()

		wos = frappe.get_all(
			"Work Order",
			filters={"production_item": "FG-001"},
			fields=["name", "qty", "sales_order"],
		)
		self.assertEqual(len(wos), 1, "expected exactly one Work Order for FG-001")
		self.assertEqual(float(wos[0].qty), 10.0)
		self.assertEqual(wos[0].sales_order, self.fixtures["sales_order"])

		# Step 5c — frepple also proposed purchases for the raw materials.
		# RM-001 is the one with a real supplier + lead time, so it must be
		# sourced from SUPP-001 rather than frepple's "Unknown supplier".
		pos = frappe.get_all(
			"Frepple Purchase Order",
			fields=["name", "item", "supplier", "quantity"],
		)
		self.assertTrue(pos, "frepple proposed no purchase orders for the raw materials")

		rm1 = [p for p in pos if p.item == "RM-001"]
		self.assertEqual(len(rm1), 1, f"expected one PO for RM-001, got {pos}")
		self.assertEqual(rm1[0].supplier, "SUPP-001")
		# 10 FG-001 × 1 RM-001 per unit.
		self.assertEqual(float(rm1[0].quantity), 10.0)

		# RM-002 has no supplier, so frepple plans it against its
		# "Unknown supplier" placeholder. That row must be skipped rather than
		# imported — and crucially, skipping it must not discard RM-001 above.
		self.assertEqual(
			[p for p in pos if p.item == "RM-002"],
			[],
			"an unsourced item was imported with frepple's placeholder supplier",
		)

	def _frepple_get(self, entity: str) -> list[dict]:
		s = self.settings
		resp = requests.get(
			f"{s.url}/api/input/{entity}/?format=json",
			auth=(s.username, s.password),
			timeout=60,
		)
		resp.raise_for_status()
		return resp.json()


@unittest.skipUnless(frepple_available(), "frepple container not reachable — run `sudo make up`")
class TestE2EFailureModes(unittest.TestCase):
	"""§6.4 — each failure mode must produce a clean error, not a mystery."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.settings = frepple_settings_configured()

	def test_wrong_password_raises_rather_than_silently_succeeding(self):
		"""A bad frepple password must surface as an HTTP error."""
		s = self.settings
		resp = requests.get(
			f"{s.url}/api/input/item/?format=json",
			auth=(s.username, "definitely-not-the-password"),
			timeout=30,
		)
		self.assertIn(resp.status_code, (401, 403))

	def test_container_down_surfaces_connection_error(self):
		"""An unreachable frepple raises ConnectionError rather than hanging."""
		with self.assertRaises(requests.exceptions.RequestException):
			requests.get("http://localhost:9099/api/input/item/", timeout=5)

	def test_unknown_entity_does_not_return_data(self):
		"""A bad API path must not look like a successful empty result.

		frepple answers an unknown ``/api/input/<x>/`` with a 302 to the login
		page rather than a 404. Following that redirect yields a 200 HTML page,
		which is exactly the trap: a typo'd entity would look like "success,
		no rows" to any caller that only checks the status code. So this
		asserts on the *unfollowed* response and on the body not being JSON.
		"""
		s = self.settings
		resp = requests.get(
			f"{s.url}/api/input/notanentity/?format=json",
			auth=(s.username, s.password),
			timeout=30,
			allow_redirects=False,
		)
		self.assertNotEqual(resp.status_code, 200)
		self.assertIn(resp.status_code, (301, 302, 404))

		# And a *valid* entity really does return a JSON list, so the check above
		# is discriminating rather than vacuous.
		good = requests.get(
			f"{s.url}/api/input/item/?format=json",
			auth=(s.username, s.password),
			timeout=30,
			allow_redirects=False,
		)
		self.assertEqual(good.status_code, 200)
		self.assertIsInstance(good.json(), list)


@unittest.skipUnless(frepple_available(), "frepple container not reachable — run `sudo make up`")
class TestE2EIframeAgainstRealFrepple(unittest.TestCase):
	"""§6.6 — the JWT the connector signs is one the real frepple accepts."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.settings = frepple_settings_configured()

	def test_signed_webtoken_is_accepted_by_frepple(self):
		"""The whole point of F14 — frepple returns 200 for our token.

		A unit test can only prove the JWT decodes with the secret *we* hold.
		Only this asserts frepple agrees, which is what risk 9 (secret drift)
		is actually about.
		"""
		from fact_frepple.fact_frepple.page._iframe import sign_jwt_url

		url = sign_jwt_url(
			f"{self.settings.url}/",
			user=self.settings.username,
			navbar=False,
			expiration=600,
		)
		resp = requests.get(url, timeout=30, allow_redirects=False)
		self.assertEqual(
			resp.status_code,
			200,
			f"frepple rejected our webtoken ({resp.status_code}) — secret drift between "
			"Frepple Settings.secret_key and the container's SECRET_KEY",
		)

	def test_tampered_webtoken_is_rejected(self):
		"""A token signed with the wrong secret must not authenticate."""
		from fact_frepple.fact_frepple.page._iframe import sign_jwt_url

		url = sign_jwt_url(
			f"{self.settings.url}/",
			user=self.settings.username,
			navbar=False,
			expiration=600,
			secret_key="not-the-frepple-secret",
		)
		resp = requests.get(url, timeout=30, allow_redirects=False)
		self.assertNotEqual(resp.status_code, 200)

	def test_csp_frame_ancestors_allows_the_bench_origin(self):
		"""§Risk 10 — the iframe is useless if CSP forbids our origin."""
		resp = requests.get(f"{self.settings.url}/", timeout=30, allow_redirects=False)
		csp = resp.headers.get("Content-Security-Policy", "")
		self.assertIn(
			"frame-ancestors",
			csp,
			"frepple sent no frame-ancestors directive — check FREPPLE_CONTENT_SECURITY_POLICY",
		)
		self.assertIn(
			"localhost:8003",
			csp,
			f"bench origin missing from frame-ancestors ({csp!r}) — the desk iframe will be "
			"blocked by the browser",
		)
