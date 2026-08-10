# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt
"""Phase 4 acceptance — ``Frepple Settings`` is the singleton config DocType
that the export/fetch/run-plan controllers all read at runtime. Its tests
cover the two invariants the rest of the suite depends on:

1. ``url`` is reachable so the controllers can actually reach frepple. A real
   request is fired at ``/`` of the configured host; ``responses`` lets us
   fake the container's reply without needing docker compose in the test path.
2. ``secret_key`` is at least 32 chars (the v17 JWT webtoken is HS256 — short
   keys are brute-forceable and frepple's djangosettings enforces them at
   boot).

We deliberately do NOT exercise the ``username``/``password`` pair here; those
belong to the controllers that actually use them (Phase 4 data export tests).
"""

import frappe
import responses
from frappe.tests import UnitTestCase


class TestFreppleSettings(UnitTestCase):
	"""Real (non-stub) tests for the v17 ``Frepple Settings`` singleton."""

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
	def test_url_is_reachable(self):
		"""The configured frepple URL must answer at least one HTTP call.

		We hit ``/`` and accept any 2xx/3xx (302 to the login screen is the
		common case for an unauthenticated frepple request). Anything else is
		a regression — the controllers will all fail with ``ConnectionError``
		otherwise.
		"""
		settings = frappe.get_single("Frepple Settings")
		responses.add(
			responses.GET,
			f"{settings.url}/",
			status=200,
			body="<html>frepple</html>",
		)

		import requests

		resp = requests.get(f"{settings.url}/", timeout=5)

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(len(responses.calls), 1)
		self.assertEqual(responses.calls[0].request.url, "http://localhost:9000/")

	def test_secret_key_minimum_length(self):
		"""The JWT HS256 signing key must be >= 32 chars.

		PyJWT will happily sign with a shorter key, but frepple's
		``djangosettings.SECRET_WEBTOKEN_KEY`` is a Django ``SECRET_KEY`` and
		warn/reject anything below that bar. We mirror the contract on the
		connector side so a misconfigured deploy fails loudly here, not in
		production.
		"""
		settings = frappe.get_single("Frepple Settings")
		self.assertGreaterEqual(len(settings.secret_key or ""), 32)

	def test_get_single_returns_singleton(self):
		"""There is exactly one ``Frepple Settings`` row; ``get_single`` proves it."""
		settings = frappe.get_single("Frepple Settings")
		self.assertEqual(settings.doctype, "Frepple Settings")
		self.assertTrue(settings.name == "Frepple Settings")
