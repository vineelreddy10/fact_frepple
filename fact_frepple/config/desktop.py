# Copyright (c) 2022, Drayang Chua and contributors
# Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
# For license information, please see license.txt

# In v17 the desk no longer reads `config/desktop.py` -- the apps-screen icon
# is created from `add_to_apps_screen` (hooks.py) and the per-workspace sidebar
# lives in `Workspace.sidebar_items` (under fact_frepple/workspace/). This file
# is kept only as a placeholder so the v14 import path stays importable. Any
# new desk-side wiring belongs in hooks.py + the workspace JSON.
