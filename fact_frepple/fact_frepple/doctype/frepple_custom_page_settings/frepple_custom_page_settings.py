# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

from typing import Any

import frappe
from frappe.model.document import Document

from fact_frepple.fact_frepple.page._iframe import sign_jwt_url


class FreppleCustomPageSettings(Document):
	pass


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