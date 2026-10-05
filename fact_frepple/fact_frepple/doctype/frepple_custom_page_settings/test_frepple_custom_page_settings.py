# -*- coding: utf-8 -*-
# Copyright (c) 2022, Drayang Chua and Contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# See license.txt
"""Phase 4 acceptance — ``get_iframe_url`` JWT webtoken round-trip.

The ``frepple_custom_page_settings.get_iframe_url`` whitelisted method returns
the iframe URL the desk form embeds into ``<iframe src=…>``. The frepple
container authenticates the request via a JWT webtoken (``?webtoken=…``);
the token must be signed with the secret stored in ``Frepple Settings`` so
the connector and the frepple container agree on the key.

The Phase 4 spec calls for one focused test: decode the token, assert it
contains ``{user, exp, navbar}``, and assert it's signed with the configured
secret. That covers the contract without overlapping the per-page iframe
tests (which exercise the per-page DocType wiring).
"""

import time

import frappe
import jwt
from frappe.tests import UnitTestCase

from fact_frepple.fact_frepple.doctype.frepple_custom_page_settings.frepple_custom_page_settings import (
	get_default_page_name,
	get_iframe_url,
)


class TestGetIframeUrl(UnitTestCase):
	"""Phase 4 acceptance — JWT webtoken in the iframe URL."""

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

		# Seed a Custom Page row keyed on page_name.
		# ``Frepple Custom Page Settings`` is a non-singleton DocType where
		# ``page_name`` is the autoname; ``frappe.get_doc`` upserts by name.
		# ``secret_key`` has ``fetch_from=frepple_settings.secret_key`` but
		# that ``fetch_from`` only runs on form load, not on insert — so we
		# set it explicitly here.
		page_name = "Default"
		if frappe.db.exists("Frepple Custom Page Settings", page_name):
			existing = frappe.get_doc("Frepple Custom Page Settings", page_name)
			existing.url = "http://localhost:9000/forecast/"
			existing.user = "admin"
			existing.expiration = 600  # in minutes (the field stores minutes)
			existing.show_navigation_bar = 0
			existing.iframe_height = 750
			existing.secret_key = "a" * 64
			existing.save()
		else:
			doc = frappe.new_doc("Frepple Custom Page Settings")
			doc.page_name = page_name
			doc.url = "http://localhost:9000/forecast/"
			doc.user = "admin"
			doc.expiration = 600
			doc.show_navigation_bar = 0
			doc.iframe_height = 750
			doc.secret_key = "a" * 64
			doc.insert()

		frappe.db.commit()
		self.page_name = page_name

	def test_get_iframe_url_returns_signed_jwt_webtoken(self):
		"""Output URL contains a JWT decodable to ``{user, exp, navbar}``."""
		before = int(time.time())
		payload = get_iframe_url(self.page_name)
		url = payload["URL"]
		height = payload["iframeHeight"]
		after = int(time.time())

		# Iframe height is round-tripped from the DocType.
		self.assertEqual(height, 750)

		# URL has the webtoken query parameter.
		self.assertIn("webtoken=", url)
		self.assertTrue(url.startswith("http://localhost:9000/forecast/"))

		# Decode the JWT and assert the contract.
		token = url.split("webtoken=", 1)[1]
		decoded = jwt.decode(
			token,
			frappe.get_single("Frepple Settings").secret_key,
			algorithms=["HS256"],
		)

		self.assertEqual(decoded["user"], "admin")
		self.assertFalse(decoded["navbar"])

		# ``expiration`` is in minutes on the DocType but seconds in the JWT —
		# the helper converts. 600 minutes = 36_000 seconds.
		expected_exp = before + 600 * 60
		self.assertGreaterEqual(decoded["exp"], expected_exp)
		self.assertLessEqual(decoded["exp"], after + 600 * 60)

	def test_get_iframe_url_token_signed_with_settings_secret(self):
		"""A token decoded with a *wrong* secret must fail verification.

		This guards against a regression where the helper hard-codes a
		different secret than ``Frepple Settings`` — frepple's djangosettings
		uses the value from ``Frepple Settings`` at boot, so a mismatch means
		the iframe returns 403 in production and the bug only surfaces there.
		"""
		payload = get_iframe_url(self.page_name)
		token = payload["URL"].split("webtoken=", 1)[1]

		# Correct secret — verify succeeds.
		secret = frappe.get_single("Frepple Settings").secret_key
		jwt.decode(token, secret, algorithms=["HS256"])

		# Wrong secret — verify fails.
		with self.assertRaises(jwt.InvalidSignatureError):
			jwt.decode(token, "wrong-secret", algorithms=["HS256"])

	def test_get_iframe_url_respects_show_navigation_bar_toggle(self):
		"""``show_navigation_bar=1`` flips the ``navbar`` claim to True."""
		doc = frappe.get_doc("Frepple Custom Page Settings", self.page_name)
		doc.show_navigation_bar = 1
		doc.save()
		frappe.db.commit()

		payload = get_iframe_url(self.page_name)
		token = payload["URL"].split("webtoken=", 1)[1]
		secret = frappe.get_single("Frepple Settings").secret_key
		decoded = jwt.decode(token, secret, algorithms=["HS256"])

		self.assertTrue(decoded["navbar"])


class TestDefaultPage(UnitTestCase):
	"""Auto-load on the Frepple Custom Page desk page picks the default row.

	The desk page calls ``get_default_page_name`` on load and renders that
	row's iframe. ``validate()`` enforces "at most one default" so the
	auto-load is unambiguous; otherwise two rows marked default would race.
	"""

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
		# Clear any leftover defaults from earlier runs so the test is
		# order-independent.
		frappe.db.sql("UPDATE `tabFrepple Custom Page Settings` SET `default` = 0")
		frappe.db.commit()

	def _make(self, page_name: str, default: int = 0) -> None:
		if frappe.db.exists("Frepple Custom Page Settings", page_name):
			frappe.delete_doc("Frepple Custom Page Settings", page_name, force=True)
		doc = frappe.new_doc("Frepple Custom Page Settings")
		doc.page_name = page_name
		doc.url = "http://localhost:9000/forecast/"
		doc.user = "admin"
		doc.expiration = 600
		doc.show_navigation_bar = 0
		doc.iframe_height = 750
		doc.secret_key = "a" * 64
		doc.default = default
		doc.insert()

	def test_get_default_returns_none_when_no_rows_marked(self):
		self._make("A")
		self._make("B")
		self.assertIsNone(get_default_page_name())

	def test_get_default_returns_the_marked_row(self):
		self._make("A")
		self._make("B", default=1)
		self.assertEqual(get_default_page_name(), "B")

	def test_validate_keeps_only_one_default(self):
		# Two rows default=1 — saving the second must clear the first.
		self._make("A", default=1)
		self._make("B", default=1)
		b = frappe.get_doc("Frepple Custom Page Settings", "B")
		b.default = 1
		b.save()
		a = frappe.get_doc("Frepple Custom Page Settings", "A")
		self.assertFalse(a.default)
		# And get_default resolves to B.
		self.assertEqual(get_default_page_name(), "B")
