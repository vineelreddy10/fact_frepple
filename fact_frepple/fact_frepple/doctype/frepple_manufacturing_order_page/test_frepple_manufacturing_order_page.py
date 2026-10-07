# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt

import frappe
from frappe.tests import UnitTestCase


class TestFreppleManufacturingOrderPage(UnitTestCase):
	"""Phase 3 acceptance — `Frepple Manufacturing Order Page` iframe URL helper."""

	def test_get_iframe_url_signs_with_frepple_settings_secret(self):
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
			"Frepple Manufacturing Order Page",
			{
				"expiration": 600,
				"user": "admin",
				"show_navigation_bar": 0,
				"url": "http://localhost:9000/data/input/manufacturingorder/",
			},
		)
		frappe.db.commit()

		from fact_frepple.fact_frepple.doctype.frepple_manufacturing_order_page.frepple_manufacturing_order_page import (
			get_iframe_url,
		)

		url = get_iframe_url()
		self.assertTrue(url.startswith("http://localhost:9000/data/input/manufacturingorder/"))
		self.assertIn("webtoken=", url)

		import jwt

		token = url.split("webtoken=", 1)[1]
		decoded = jwt.decode(token, "phase3-test-secret", algorithms=["HS256"])
		self.assertEqual(decoded["user"], "admin")
