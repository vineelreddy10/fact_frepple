# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt

import frappe
from frappe.tests import UnitTestCase


class TestFreppleSupplyPathPage(UnitTestCase):
	"""Phase 3 acceptance — `Frepple Supply Path Page` iframe URL helper.

	The Supply Path view is unique among the 5 single-row pages because it
	optionally filters by a specific demand name (a Frepple Demand mirror
	row). The test covers the demand-filter branch and asserts that the JWT
	is still signed by `Frepple Settings.secret_key`.
	"""

	def test_get_iframe_url_with_demand_filter(self):
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
		frappe.db.set_single_value(
			"Frepple Supply Path Page",
			{
				"expiration": 600,
				"user": "admin",
				"show_navigation_bar": 0,
				"url": "http://localhost:9000/supplypath/demand/",
				"demand": "SO-001",
			},
		)
		frappe.db.commit()

		from fact_frepple.fact_frepple.doctype.frepple_supply_path_page.frepple_supply_path_page import (
			get_iframe_url,
		)

		url = get_iframe_url()
		self.assertIn("/supplypath/demand/SO-001/", url)
		self.assertIn("webtoken=", url)

		import jwt

		token = url.split("webtoken=", 1)[1]
		decoded = jwt.decode(token, "phase3-test-secret", algorithms=["HS256"])
		self.assertEqual(decoded["user"], "admin")
