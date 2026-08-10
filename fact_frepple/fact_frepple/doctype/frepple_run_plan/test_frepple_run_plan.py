# -*- coding: utf-8 -*-
# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt

import json
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan import (
	run_plan,
)


class TestFreppleRunPlan(UnitTestCase):
	"""Phase 3 acceptance — `Frepple Run Plan` DocType.

	Verifies that ``run_plan`` POSTs to the v9 path ``/api/runplan/`` (not
	the v14 ``/execute/api/runplan/`` which doesn't exist on frepple 9.x)
	and that the constraint flags are translated into the right query
	parameters.
	"""

	def setUp(self):
		frappe.db.set_single_value(
			"Frepple Settings",
			{
				"url": "http://localhost:9000",
				"username": "admin",
				"password": "admin",
				"authorization_header": "",
				"secret_key": "phase3-test-secret",
				"wip_location_name": "Work In Progress",
			},
		)
		frappe.db.commit()

	def test_run_plan_posts_to_v9_runplan_endpoint(self):
		doc = json.dumps({
			"constraint": 1,
			"unconstraint": 0,
			"capacity": 1,
			"lead_time": 1,
			"release_fence": 0,
			"update_frepple": 0,
		})

		with patch(
			"fact_frepple.fact_frepple.doctype.frepple_run_plan.frepple_run_plan.make_post_request",
			return_value={"ok": True},
		) as mock_post:
			run_plan(doc)

		self.assertEqual(mock_post.call_count, 1)
		kwargs = mock_post.call_args.kwargs
		url = mock_post.call_args.args[0] if mock_post.call_args.args else kwargs.get("url", "")

		# v17 — frepple 9.x dropped /execute/api/runplan/ in favor of /api/runplan/
		self.assertIn("/api/runplan/", url)
		self.assertNotIn("/execute/api/runplan/", url)

		# capacity(4) + lead_time(1) + constrained plantype(1)
		self.assertIn("constraint=5", url)
		self.assertIn("plantype=1", url)
		self.assertIn("env=supply", url)
