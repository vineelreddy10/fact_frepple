# Copyright (c) 2026, fact_frepple contributors
# For license information, please see license.txt
"""Regression — page-side ``get_iframe_url`` ``frappe.call`` method paths.

The 2026-08-13 rename of the four slug-colliding singletons moved the
DocType folders and Python controllers but missed the four Desk Page
``.js`` files that invoke the whitelisted ``get_iframe_url`` via
``frappe.call``. The pages then rendered an empty app shell because
Frappe raised ``No module named
'fact_frepple.fact_frepple.doctype.<old_slug>'`` when the desk Page
tried to resolve the iframe URL.

This test asserts each affected page ``.js`` references the renamed
module path so a future rename pass that touches the Python side but
forgets the client side will fail loudly in CI.

See ``specs/page-route-preemption.md`` for the full write-up.
"""

from __future__ import annotations

import os
import re
import unittest

from frappe.tests import UnitTestCase

PAGE_DIR = os.path.dirname(os.path.abspath(__file__))


# (Desk Page folder, old slug before rename, new slug after rename). Each
# pair mirrors the rename the 2026-08-13 patch performed on
# ``tab<old>`` → ``tab<new>``.
RENAMED_SLUGS = (
	("supply_path_page", "supply_path_page", "frepple_supply_path_page"),
	("manufacturing_order_page", "manufacturing_order_page", "frepple_manufacturing_order_page"),
	("purchase_order_page", "purchase_order_page", "frepple_purchase_order_page"),
	("resource_report_page", "resource_report_page", "frepple_resource_report_page"),
)

# ``getSettings`` always invokes ``frappe.call({'method': '…'})`` with this
# literal prefix; we don't care about case but we do care that the path
# points at the renamed module, not the pre-rename one.
METHOD_PATH_RE = re.compile(
	r"""['"]method['"]\s*:\s*['"]fact_frepple\.fact_frepple\.doctype\.([^'"]+)['"]""",
)


class TestPageIframeMethodPaths(UnitTestCase):
	"""Regression for the 2026-08-13 page JS method-path miss."""

	def _read_method_path(self, page_folder: str) -> str | None:
		js_path = os.path.join(PAGE_DIR, page_folder, f"{page_folder}.js")
		with open(js_path, encoding="utf-8") as handle:
			contents = handle.read()
		match = METHOD_PATH_RE.search(contents)
		self.assertIsNotNone(
			match,
			f"Could not find a 'method' path in {js_path}; the test is stale",
		)
		return match.group(1)

	def test_renamed_pages_reference_the_new_module(self):
		for page_folder, _old_slug, new_slug in RENAMED_SLUGS:
			with self.subTest(page=page_folder):
				path = self._read_method_path(page_folder)
				self.assertEqual(
					path,
					f"{new_slug}.{new_slug}.get_iframe_url",
					f"{page_folder}/{page_folder}.js still points at the pre-rename "
					f"module path '{path}'. After the rename it must reference "
					f"'{new_slug}.{new_slug}.get_iframe_url'.",
				)

	def test_renamed_pages_do_not_reference_the_old_module(self):
		# Belt-and-braces: even if someone reorders the previous test, this
		# fails on the exact regression we shipped in 2026-08-13. Check the
		# bare old slug as a segment of the path (``doctype.<slug>.<slug>``),
		# not as a substring — the new slug (``frepple_<slug>``) contains the
		# old slug as a substring and would trip a naive ``assertNotIn``.
		old_module_re = re.compile(
			r"\.doctype\."  # doctype boundary
			r"(?<![A-Za-z0-9_])"  # not preceded by a slug character
			r"(" + "|".join(re.escape(old) for _, old, _ in RENAMED_SLUGS) + r")"
			r"\."
		)
		for page_folder, _old_slug, _new_slug in RENAMED_SLUGS:
			with self.subTest(page=page_folder):
				js_path = os.path.join(PAGE_DIR, page_folder, f"{page_folder}.js")
				with open(js_path, encoding="utf-8") as handle:
					contents = handle.read()
				self.assertIsNone(
					old_module_re.search(contents),
					f"{page_folder}/{page_folder}.js still has the bare old "
					f"slug in its method path. Frappe logs 'No module named "
					f"fact_frepple.fact_frepple.doctype.<old_slug>' and the "
					f"iframe never loads.",
				)


if __name__ == "__main__":
	unittest.main()
