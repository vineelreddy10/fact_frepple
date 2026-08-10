# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

from typing import Any

import frappe
from frappe.model.document import Document

import jwt
import time


class FreppleCustomPageSettings(Document):
	pass


@frappe.whitelist()
def get_iframe_url(page_name: str) -> dict[str, Any]:
	doc = frappe.get_doc("Frepple Custom Page Settings", page_name)
	doc_2 = frappe.get_doc("Frepple Settings")

	# F14: PyJWT 2.x returns str directly; the v14 source called .decode("ascii").
	webtoken = jwt.encode(
		{
			"exp": round(time.time()) + doc.expiration,
			"user": doc.user,
			"navbar": bool(doc.show_navigation_bar),
		},
		doc_2.secret_key,
		algorithm="HS256",
	)

	return {
		"iframeHeight": doc.iframe_height,
		"URL": doc.url + "?webtoken=" + webtoken,
	}


@frappe.whitelist()
def get_secret_key() -> str:
	doc_2 = frappe.get_doc("Frepple Settings")
	return doc_2.secret_key