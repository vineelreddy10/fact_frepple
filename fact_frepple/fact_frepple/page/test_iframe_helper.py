# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt
"""Unit tests for the shared ``sign_jwt_url`` helper."""

import time
from unittest.mock import patch

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
		self.assertLessEqual(decoded["exp"], int(time.time()) + 600)

	def test_exp_truncates_subsecond_now(self):
		"""``exp`` must be ``int(now) + expiration`` — never rounded up.

		Rounding a fractional ``time.time()`` up puts ``exp`` one second beyond
		``int(time.time()) + expiration``, which trips any caller that bounds
		the token lifetime against a truncated clock read.
		"""
		with patch("fact_frepple.fact_frepple.page._iframe.time.time", return_value=1000.9):
			url = sign_jwt_url(
				"http://localhost:9000/x/",
				user="admin",
				navbar=False,
				expiration=600,
				secret_key="override-secret",
			)
		token = url.split("webtoken=", 1)[1]
		decoded = jwt.decode(
			token,
			"override-secret",
			algorithms=["HS256"],
			options={"verify_exp": False},
		)
		self.assertEqual(decoded["exp"], 1600)

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

	def test_missing_secret_key_raises_actionable_error(self):
		"""Regression: when ``Frepple Settings.secret_key`` is empty, signing
		fails with a clear, actionable error instead of pyjwt's opaque
		``TypeError: Expected a string value`` (see issue: empty settings
		crashed the iframe helper with a stack trace from inside pyjwt).
		"""
		original = frappe.get_single("Frepple Settings").secret_key
		frappe.db.set_single_value("Frepple Settings", "secret_key", None)
		frappe.db.commit()
		try:
			with self.assertRaises(frappe.ValidationError) as ctx:
				sign_jwt_url(
					"http://localhost:9000/data/input/demand/",
					user="admin",
					navbar=False,
					expiration=600,
				)
			self.assertIn("secret_key", str(ctx.exception))
			self.assertIn("Frepple Settings", str(ctx.exception))
		finally:
			frappe.db.set_single_value("Frepple Settings", "secret_key", original)
			frappe.db.commit()
