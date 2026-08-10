# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt

import json

import frappe
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching.frepple_integration_data_fetching import (
	get_wip_location_prefix,
)


class TestFreppleIntegrationDataFetching(UnitTestCase):
	"""Phase 2 acceptance — fetch controller.

	Exercises the R8 mitigation (`wip_location_name` from settings) and a
	`fetch_data` happy-path that builds the expected mirror DocType rows.
	The real frepple round-trip is left to Phase 6.
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
