#!/usr/bin/env bash
# Phase 2 — bulk mirror DocType copy.
#
# For each doctype folder under $SRC, copy it to $DST and apply the v17
# transforms spelled out in specs/migrate-v17.md §6 (F1-F14) and §9.
#
# Idempotent: once a destination folder has been transformed, a marker
# file (.fact_frepple_migrated) is written; re-runs become no-ops for
# files already present, only filling in missing test stubs. Manual edits
# (type annotations, wip_location_name, F14 fixes) on the migrated files
# are preserved across re-runs.
#
# Usage:
#   SRC=/tmp/opencode/erpnext_frepple_connector \
#   DST=$PWD/fact_frepple/fact_frepple \
#   scripts/migrate_phase2.sh [--force] <doctype...>

set -euo pipefail

SRC="${SRC:-/tmp/opencode/erpnext_frepple_connector}"
DST="${DST:-$PWD/fact_frepple/fact_frepple}"
SRC_DOCTYPES="$SRC/frepple/frepple/doctype"
DST_DOCTYPES="$DST/doctype"
MARKER=".fact_frepple_migrated"

force=0
for arg in "$@"; do
	if [[ "$arg" == "--force" ]]; then
		force=1
		shift
		break
	fi
done

if [[ $# -eq 0 ]]; then
	echo "Usage: $0 [--force] <doctype...>" >&2
	exit 2
fi

for name in "$@"; do
	src_dir="$SRC_DOCTYPES/$name"
	dst_dir="$DST_DOCTYPES/$name"

	if [[ ! -d "$src_dir" ]]; then
		echo "skip: $name (no source dir $src_dir)" >&2
		continue
	fi

	migrated_marker="$dst_dir/$MARKER"

	if [[ -f "$migrated_marker" && $force -eq 0 ]]; then
		# Idempotent path: only fill in missing test files.
		for src_file in "$src_dir"/test_*.py; do
			[[ -e "$src_file" ]] || continue
			base="$(basename "$src_file")"
			if [[ ! -e "$dst_dir/$base" ]]; then
				cp "$src_file" "$dst_dir/$base"
				echo "  +test $name/$base"
			fi
		done
		echo "idempotent: $name"
		continue
	fi

	rm -rf "$dst_dir"
	mkdir -p "$dst_dir"

	for f in "$src_dir"/*; do
		base="$(basename "$f")"
		cp "$f" "$dst_dir/$base"
	done

	# F6 — drop 'from __future__ import unicode_literals'
	find "$dst_dir" -type f -name "*.py" -exec sed -i '/^from __future__ import unicode_literals$/d' {} +

	# D3 / F9 — module path rewrite.
	# Source layout is `frepple.frepple.<area>...`; target is `fact_frepple.fact_frepple.<area>...`.
	find "$dst_dir" -type f -name "*.py" -exec sed -i 's|from frepple\.frepple\.|from fact_frepple.fact_frepple.|g' {} +
	find "$dst_dir" -type f -name "*.py" -exec sed -i 's|import frepple\.frepple\.|import fact_frepple.fact_frepple.|g' {} +
	find "$dst_dir" -type f -name "*.js" -exec sed -i 's|from frepple\.frepple\.|from fact_frepple.fact_frepple.|g' {} +
	find "$dst_dir" -type f -name "*.json" -exec sed -i 's|"module": "Frepple"|"module": "Fact Frepple"|g' {} +

	# F1 — get_request_session removed; drop the import (call sites fixed in Phase 4).
	find "$dst_dir" -type f -name "*.py" -exec sed -i '/^from frappe.utils import get_request_session$/d' {} +
	find "$dst_dir" -type f -name "*.py" -exec sed -i '/^from frappe.utils import get_request_session, /d' {} +
	find "$dst_dir" -type f -name "*.py" -exec sed -i 's|, get_request_session||g' {} +
	find "$dst_dir" -type f -name "*.py" -exec sed -i 's|get_request_session, ||g' {} +

	# F3 — ensure sort_field / sort_order present in DocType JSON metadata
	for json in "$dst_dir"/*.json; do
		[[ -e "$json" ]] || continue
		if ! grep -q '"sort_field"' "$json"; then
			sed -i 's|"track_changes": 1|"sort_field": "modified",\n "sort_order": "DESC",\n "track_changes": 1|' "$json"
		fi
	done

	# Header attribution
	for py in "$dst_dir"/*.py; do
		[[ -e "$py" ]] || continue
		# only add if not already present
		if ! grep -q "Ported to fact_frepple" "$py"; then
			sed -i '2a # Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.' "$py"
		fi
	done

	touch "$migrated_marker"
	echo "migrated: $name"
done
