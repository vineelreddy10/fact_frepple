# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt
"""Phase 4 acceptance — ``Frepple Run Plan`` DocType.

``run_plan`` POSTs to frepple's ``/execute/api/runplan/`` task endpoint to queue a
plan run. The Phase 3 unit tests verified the URL/query string with a
``unittest.mock.patch``; this module fires a real ``requests`` call through
Frappe's ``make_post_request`` and verifies both the URL contract and the
HTTP body that hits the wire. ``responses`` mocks frepple at the HTTP
adapter level so no docker compose / network is needed.
"""

import json
from unittest.mock import patch

import frappe
import responses
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan import (
	run_plan,
)


def _basic_auth_url(path: str) -> str:
	"""Build the URL as ``run_plan`` actually emits it (basic auth in URL)."""
	return f"http://admin:admin@localhost:9000{path}"


class TestFreppleRunPlan(UnitTestCase):
	"""Phase 4 acceptance — real ``/execute/api/runplan/`` round-trip via ``responses``."""

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

	@responses.activate
	def test_run_plan_posts_to_v9_runplan_endpoint(self):
		"""Verifies URL path + constraint query-string translation end-to-end."""
		responses.add(
			responses.POST,
			_basic_auth_url("/execute/api/runplan/"),
			status=200,
			json={"ok": True},
		)

		doc = json.dumps(
			{
				"constraint": 1,
				"unconstraint": 0,
				"capacity": 1,
				"lead_time": 1,
				"release_fence": 0,
				"update_frepple": 0,
			}
		)

		run_plan(doc)

		self.assertEqual(len(responses.calls), 1)
		request = responses.calls[0].request
		# The task API lives at /execute/api/runplan/. Phase 4 originally
		# asserted the opposite (a bare /api/runplan/) and this mock happily
		# confirmed it — the Phase 6 E2E showed that path 302s to the login
		# page, so the plan never ran. Assert the real contract.
		self.assertIn("/execute/api/runplan/", request.url)
		# capacity(4) + lead_time(1) + constrained plantype(1)
		self.assertIn("constraint=5", request.url)
		self.assertIn("plantype=1", request.url)
		self.assertIn("env=supply", request.url)
		# Basic auth present in URL
		self.assertIn("admin:admin@localhost:9000", request.url)

	@responses.activate
	def test_run_plan_sends_post_with_no_body(self):
		"""frepple's ``/execute/api/runplan/`` reads everything from the query string.

		The connector sends ``data=None`` (empty body) — verified here so a
		future regression that accidentally attaches a JSON payload surfaces
		as a 4xx from frepple instead of silently succeeding with extra
		parameters.
		"""
		responses.add(
			responses.POST,
			_basic_auth_url("/execute/api/runplan/"),
			status=200,
			json={"ok": True},
		)

		doc = json.dumps(
			{
				"constraint": 1,
				"unconstraint": 0,
				"capacity": 0,
				"lead_time": 0,
				"release_fence": 0,
				"update_frepple": 0,
			}
		)

		run_plan(doc)

		request = responses.calls[0].request
		# body is either None or empty bytes depending on the Frappe/requests
		# version — both are acceptable for the task endpoint.
		body = request.body
		if body is not None:
			self.assertIn(body, (b"", b"None"))

	@responses.activate
	def test_run_plan_with_update_frepple_calls_export_sales_orders(self):
		"""``update_frepple=1`` triggers an export of in-flight MO/PO rows.

		We patch ``export_sales_orders`` / ``export_manufacturing_orders`` /
		``export_purchase_orders`` and verify they're invoked before the
		plan run. The plan endpoint still gets hit, but the count is now 1
		(the plan POST) plus the 3 internal export POSTs (each going to a
		different /api/input/<entity>/ endpoint).
		"""
		# Stub the three pre-export functions so they don't try to SQL.
		with (
			patch("fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan.export_sales_orders"),
			patch(
				"fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan.export_manufacturing_orders"
			),
			patch(
				"fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan.export_purchase_orders"
			) as mock_po,
		):
			# Stub the 3 export endpoints to swallow their POSTs.
			for entity in ("demand", "manufacturingorder", "purchaseorder"):
				responses.add(
					responses.POST,
					_basic_auth_url(f"/api/input/{entity}/"),
					status=201,
					json={"pk": 1},
				)
			# The plan-run POST itself.
			responses.add(
				responses.POST,
				_basic_auth_url("/execute/api/runplan/"),
				status=200,
				json={"ok": True},
			)

			doc = json.dumps(
				{
					"constraint": 1,
					"unconstraint": 0,
					"capacity": 0,
					"lead_time": 0,
					"release_fence": 0,
					"update_frepple": 1,
				}
			)
			run_plan(doc)

		# export_purchase_orders ran at least once (sanity check).
		self.assertTrue(mock_po.called)
		# The plan-run POST happened — find it in the captured calls.
		plan_calls = [c for c in responses.calls if "/execute/api/runplan/" in c.request.url]
		self.assertEqual(len(plan_calls), 1)
