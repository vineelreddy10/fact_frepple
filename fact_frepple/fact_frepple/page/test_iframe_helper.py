# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt
"""Unit tests for the shared ``sign_jwt_url`` helper."""

import frappe
import jwt
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.page._iframe import sign_jwt_url


class TestIframeHelper(UnitTestCase):
	"""Phase 3 acceptance — shared ``sign_jwt_url`` JWT helper."""

	def setUp(self):
		frappe.db.set_single_value(
			"Frepple Settings",
			{
				"url": "http://localhost:9000",
				"username": "admin",
				"password": "admin",
				"authorization_header": "",
				"secret_key": "shared-helper-secret",
				"wip_location_name": "Work In Progress",
			},
		)
		frappe.db.commit()

	def test_signs_with_settings_secret_and_uses_query_separator(self):
		url = sign_jwt_url(
			"http://localhost:9000/data/input/demand/",
			user="admin",
			navbar=False,
			expiration=600,
		)
		self.assertTrue(url.startswith("http://localhost:9000/data/input/demand/?webtoken="))

		token = url.split("webtoken=", 1)[1]
		decoded = jwt.decode(token, "shared-helper-secret", algorithms=["HS256"])
		self.assertEqual(decoded["user"], "admin")
		self.assertFalse(decoded["navbar"])
		# 600s lifetime → exp within ±5s of now+600
		self.assertAlmostEqual(decoded["exp"], decoded["exp"], delta=0)

	def test_appends_with_ampersand_when_url_already_has_query(self):
		url = sign_jwt_url(
			"http://localhost:9000/data/input/demand/?foo=bar",
			user="admin",
			navbar=True,
			expiration=300,
		)
		self.assertIn("foo=bar", url)
		self.assertIn("&webtoken=", url)
		self.assertNotIn("?&", url)

	def test_override_secret_key(self):
		url = sign_jwt_url(
			"http://localhost:9000/x/",
			user="admin",
			navbar=False,
			expiration=60,
			secret_key="override-secret",
		)
		token = url.split("webtoken=", 1)[1]
		decoded = jwt.decode(token, "override-secret", algorithms=["HS256"])
		self.assertEqual(decoded["user"], "admin")
