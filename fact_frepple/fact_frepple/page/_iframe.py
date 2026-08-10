# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt
"""Shared helpers for the frepple iframe desk pages.

The 6 desk pages (Custom Page + Demand + Manufacturing Order + Purchase Order
+ Resource Report + Supply Path) all wrap a frepple UI view in an iframe.
frepple 9.x authenticates the iframe via a JWT webtoken appended as
``?webtoken=<jwt>`` to the URL (see ``ANALYSIS_AND_MIGRATION_PLAN.md`` §7).

This module centralises the JWT signing so every page delegates to one helper.
Each per-page DocType still owns its own URL + per-page config (URL default,
show-navigation-bar toggle, optional demand filter for supply-path); only the
JWT-signing primitives live here.
"""

from __future__ import annotations

import time

import frappe
import jwt


def _settings() -> "frappe.model.document.Document":
	"""Return the singleton Frepple Settings row.

	Centralised so a missing/unsaved settings record fails in one place with
	a clear error rather than an opaque AttributeError down the call chain.
	"""
	return frappe.get_single("Frepple Settings")


def sign_jwt_url(
	url: str,
	*,
	user: str,
	navbar: bool,
	expiration: int,
	secret_key: str | None = None,
) -> str:
	"""Append ``?webtoken=<jwt>`` to ``url`` using ``secret_key`` (defaults to Frepple Settings).

	Args:
		url: Absolute frepple view URL the iframe will load.
		user: frepple username to impersonate inside the iframe.
		navbar: ``True`` to render frepple's top nav inside the iframe.
		expiration: Token lifetime in seconds (the source DocTypes store minutes;
		    callers convert before calling).
		secret_key: HS256 signing secret. Falls back to ``Frepple Settings.secret_key``.

	Returns:
		The ``url`` with ``?webtoken=<jwt>`` (or ``&webtoken=<jwt>`` if ``url``
		already has a query string) appended.
	"""
	if not secret_key:
		secret_key = _settings().secret_key

	webtoken = jwt.encode(
		{
			# Truncate rather than round: rounding up can push ``exp`` a second
			# past a caller's ``int(time.time()) + expiration`` upper bound.
			"exp": int(time.time()) + int(expiration),
			"user": user,
			"navbar": bool(navbar),
		},
		secret_key,
		algorithm="HS256",
	)

	separator = "&" if "?" in url else "?"
	return f"{url}{separator}webtoken={webtoken}"
