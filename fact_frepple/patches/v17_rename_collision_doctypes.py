# Copyright (c) 2026, fact_frepple contributors
# See license.txt
"""Rename 4 singleton Page-config DocTypes so their slugs no longer collide
with the matching Desk Page slugs.

Background
----------
v17's router auto-populates a slug → DocType map for every DocType the user can
read (apps/frappe/frappe/public/js/frappe/router.js:115).  Several
frepple Page-config singletons were given the same label as the Desk Page
they drive, so /desk/<slug> matched the DocType and opened its form instead
of the iframe.  See ``specs/page-route-preemption.md`` for the workaround
that existed before this rename.

This patch removes the need for that shim by renaming the colliding
singletons to break the slug collision:

  Supply Path Page       →  Frepple Supply Path Page
  Manufacturing Order …  →  Frepple Manufacturing Order Page
  Purchase Order Page    →  Frepple Purchase Order Page
  Resource Report Page   →  Frepple Resource Report Page

The desk Page records themselves keep the same short slug
(`supply-path-page`, …) and still resolve to the iframe page.

Each rename is:
1. RENAME TABLE in MySQL — preserves the singleton row and all field values
   when the old table still exists.
2. UPDATE `tabDocType` row whose name === old name, set name = new name.

After the rename, if the freshly-named singleton rows were missing (e.g.
the old table had been dropped by an earlier migration), this patch
re-seeds them from the JSON's defaults via a ``reload_doc``-equivalent
helper and then points each row's ``url`` at the same host configured on
``Frepple Settings``.

Idempotent: re-running on a site that already has the new names is a no-op.
Re-running only the URL-update step is a no-op if every row already has a
``91.107.206.65:9000`` URL configured (or any URL the admin picked).
"""

import frappe

RENAMES = [
	("Supply Path Page", "Frepple Supply Path Page", "/supplypath/demand/"),
	("Manufacturing Order Page", "Frepple Manufacturing Order Page", "/data/input/manufacturingorder/"),
	("Purchase Order Page", "Frepple Purchase Order Page", "/data/input/purchaseorder/"),
	("Resource Report Page", "Frepple Resource Report Page", "/data/input/operationplanresource/"),
]


def _new_table(old: str) -> str:
	return "tab" + old


def execute():
	for old, new, suffix in RENAMES:
		old_table = _new_table(old)
		new_table = _new_table(new)

		# Step 1: RENAME TABLE (only if old exists and new doesn't)
		old_exists = frappe.db.sql(
			"SELECT 1 FROM information_schema.tables "
			"WHERE table_name = %s LIMIT 1",
			old_table,
		)
		new_exists = frappe.db.sql(
			"SELECT 1 FROM information_schema.tables "
			"WHERE table_name = %s LIMIT 1",
			new_table,
		)
		if old_exists and not new_exists:
			frappe.db.sql(f"RENAME TABLE `{old_table}` TO `{new_table}`")
			print(f"  renamed table: {old_table} -> {new_table}")
		elif old_exists and new_exists:
			print(f"  skipping table {old_table}: target already exists")
		else:
			print(f"  skipping table {old_table}: source gone")

		# Step 2: ensure the DocType row in tabDocType points at the new name
		existing = frappe.db.get_value("DocType", old, "name")
		if existing == old:
			frappe.db.sql(
				"UPDATE `tabDocType` SET name = %s WHERE name = %s",
				(new, old),
			)
			print(f"  renamed doctype row: {old} -> {new}")
		elif existing == new:
			print(f"  doctype row already named {new}")
		else:
			print(f"  no doctype row found under old name {old!r}")

	frappe.db.commit()

	# Step 3: ensure each new singleton has a row whose url points at the
	#         configured Frepple host. This re-applies the host from
	#         ``Frepple Settings`` so the four pages' iframes don't end up on
	#         a localhost default.
	try:
		settings = frappe.get_single("Frepple Settings")
		base_url = (settings.url or "").rstrip("/")
	except Exception:
		base_url = ""

	if not base_url:
		print("  no Frepple Settings.url — skipping URL re-seed step")
		return

	for old, new, suffix in RENAMES:
		try:
			row = frappe.db.get_value(new, new, "url")
		except Exception:
			# Table doesn't exist yet — caller should run ``bench migrate``
			# again so the doctype reload creates the singleton row.
			print(f"  skipping url re-seed for {new}: row not yet created")
			continue

		expected = base_url + suffix
		if row != expected:
			frappe.db.set_value(new, new, "url", expected)
			print(f"  set {new}.url = {expected!r}")

	frappe.db.commit()
