# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

from typing import Any

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from fact_frepple.fact_frepple.page._iframe import sign_jwt_url


class FreppleCustomPageSettings(Document):
	def validate(self):
		# Mutually exclusive: at most one row may carry default=1. Without
		# this, the auto-load on the Frepple Custom Page desk page would be
		# ambiguous and the operator would have to guess which page renders.
		if cint(self.default):
			frappe.db.sql(
				"UPDATE `tabFrepple Custom Page Settings` SET `default` = 0 "
				"WHERE `name` != %s AND `default` = 1",
				self.name,
			)


@frappe.whitelist()
def get_iframe_url(page_name: str) -> dict[str, Any]:
	doc = frappe.get_doc("Frepple Custom Page Settings", page_name)

	return {
		"iframeHeight": doc.iframe_height,
		"URL": sign_jwt_url(
			doc.url,
			user=doc.user,
			navbar=bool(doc.show_navigation_bar),
			# v17 — DocType field ``expiration`` is documented as "in minutes"
			# but ``sign_jwt_url`` consumes seconds. Convert here so the JWT
			# lifetime matches the user's intent (Phase 4 test exposed the gap).
			expiration=doc.expiration * 60,
		),
	}


@frappe.whitelist()
def get_secret_key() -> str:
	return frappe.get_single("Frepple Settings").secret_key


@frappe.whitelist()
def get_default_page_name() -> str | None:
	"""Return the page_name of the row marked ``default=1``, or ``None``.

	The Frepple Custom Page desk page calls this on load to auto-render one
	row's iframe without forcing the operator to pick from the dropdown.
	"""
	rows = frappe.get_all(
		"Frepple Custom Page Settings",
		filters={"default": 1},
		pluck="page_name",
		limit=1,
	)
	return rows[0] if rows else None