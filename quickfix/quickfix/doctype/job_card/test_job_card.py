# Copyright (c) 2026, Kaviya and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase
from quickfix.quickfix.doctype.job_card.job_card import JobCard
from quickfix.quickfix.overrides.custom_job_card import CustomJobCard


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestJobCard(IntegrationTestCase):
	"""
	Integration tests for JobCard.
	Use this class for testing interactions between multiple components.
	"""

	def custom_job_card_validate_must_call_parent_validate(self):
		"""Catch missing super().validate() in the custom controller override."""
		parent_validate_called = {"called": False}
		original_validate = JobCard.validate

		def patched_parent_validate(self):
			parent_validate_called["called"] = True
			return None

		JobCard.validate = patched_parent_validate
		try:
			doc = CustomJobCard({"doctype": "Job Card"})
			doc.priority = "Urgent"
			doc.assigned_technician = None
			doc.validate()
			self.assertTrue(
				parent_validate_called["called"],
				"CustomJobCard.validate must call super().validate() to preserve base JobCard validation.",
			)
		finally:
			JobCard.validate = original_validate
