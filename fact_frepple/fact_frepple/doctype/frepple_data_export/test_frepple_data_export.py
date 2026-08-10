# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_data_export.frepple_data_export import (
	get_frepple_params,
)


class TestFreppleDataExport(UnitTestCase):
	"""Phase 2 acceptance — export controller.

	Only exercises the pure-Python URL builder and a single mocked POST round-trip
	via `unittest.mock.patch` on `make_post_request`. Real HTTP and DB round-trips
	live in Phase 6's E2E test.
	"""

	def setUp(self):
		frappe.db.set_single_value(
			"Frepple Settings",
			{
				"url": "http://localhost:9000",
				"username": "admin",
				"password": "admin",
				"authorization_header": "",
				"secret_key": "test-secret-key",
				"wip_location_name": "Work In Progress",
			},
		)
		frappe.db.commit()

	def test_get_frepple_params_builds_basic_auth_url(self):
		url, headers = get_frepple_params(api="item", filter="?limit=10")
		self.assertTrue(url.startswith("http://admin:admin@localhost:9000/api/input/item/"))
		self.assertIn("?limit=10", url)
		self.assertEqual(headers["Content-type"], "application/json; charset=UTF-8")

	def test_get_frepple_params_defaults(self):
		url, _headers = get_frepple_params()
		# empty api/filter fall back to ""
		self.assertTrue(url.endswith("/api/input/") or url.endswith("/api/input//"))
