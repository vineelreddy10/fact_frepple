# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from fact_frepple.fact_frepple.page._iframe import sign_jwt_url


class ResourceReportPage(Document):
	pass


@frappe.whitelist()
def get_iframe_url() -> str:
	doc = frappe.get_doc("Resource Report Page")

	return sign_jwt_url(
		doc.url,
		user=doc.user,
		navbar=bool(doc.show_navigation_bar),
		expiration=doc.expiration,
	)
