# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt
"""``bench fact-frepple`` commands.

Registered via the ``commands`` hook in ``hooks.py``.
"""

import subprocess

import click
import frappe
from frappe.commands import get_site, pass_context


@click.command("fact-frepple-e2e")
@click.option("--skip-fixtures", is_flag=True, help="Assume ERPNext fixtures already exist.")
@pass_context
def e2e(context, skip_fixtures=False):
	"""Run the Phase 6 end-to-end transfer test against the configured frepple.

	Requires the frepple stack up (``cd docker && sudo make up``) and a
	``frepple_e2e`` block in ``site_config.json`` — see ``docker/README.md``.
	"""
	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		from fact_frepple.tests.e2e.helpers import e2e_config, frepple_available

		conf = e2e_config()
		if not conf.get("url"):
			click.secho(
				"No frepple E2E config found (site_config.json → frepple_e2e).", fg="red"
			)
			raise SystemExit(1)

		if not frepple_available():
			click.secho(
				f"frepple at {conf['url']} is not reachable — is the container up?", fg="red"
			)
			raise SystemExit(1)

		click.secho(f"frepple reachable at {conf['url']}", fg="green")

		if not skip_fixtures:
			from fact_frepple.tests.e2e import fixtures

			created = fixtures.create_all()
			click.secho(f"fixtures ready: {created}", fg="green")
	finally:
		frappe.destroy()

	# Shell out to `bench run-tests` rather than calling the runner in-process:
	# v17 replaced `frappe.test_runner.main` with the `frappe.testing` package,
	# and binding to either internal API breaks on the next reshuffle.
	cmd = [
		"bench",
		"--site",
		site,
		"run-tests",
		"--app",
		"fact_frepple",
		"--module",
		"fact_frepple.tests.e2e.test_e2e_two_way",
	]
	click.echo(" ".join(cmd))
	raise SystemExit(subprocess.call(cmd))


commands = [e2e]
