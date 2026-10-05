# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from fact_frepple.fact_frepple.page._iframe import sign_jwt_url


class FreppleSupplyPathPage(Document):
	pass


@frappe.whitelist()
def get_iframe_url() -> str:
	doc = frappe.get_doc("Frepple Supply Path Page")

	# Optional demand filter — if the operator pinned a specific demand, append
	# its name to the URL; otherwise pick the first mirror-row.
	demand_to_show = ""
	if doc.demand:
		demand_to_show = doc.demand
	else:
		demands = frappe.db.get_list("Frepple Demand")
		if demands:
			demand_to_show = demands[0].name

	url = doc.url + demand_to_show + "/"

	return sign_jwt_url(
		url,
		user=doc.user,
		navbar=bool(doc.show_navigation_bar),
		expiration=doc.expiration,
	)
