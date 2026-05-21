import json
from pathlib import Path

import frappe


def load_test_fixtures():

    fixtures_path = Path(__file__).parent / "fixtures"

    fixture_files = [
        "quickfix_settings.json",
        "device_type.json",
        "test_roles.json",
    ]

    for file_name in fixture_files:

        file_path = fixtures_path / file_name

        with open(file_path) as f:
            records = json.load(f)

        for record in records:
                frappe.get_doc(record).insert(
                    ignore_if_duplicate=True
                )
                frappe.db.commit()
