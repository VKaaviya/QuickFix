import frappe
def apply_all():
    patch_get_url()
def patch_get_url():
    """
    WHY: Site uses a custom CDN prefix stored in site_config.
    WHAT: Prepends custom_url_prefix to all generated URLs.
    VERSION TESTED: frappe v16.x
    RISK: If frappe.utils.get_url signature changes, this will fail.
    TEST: test_monkey_patches.py::TestGetUrl
    """
    import frappe.utils as fu
    if hasattr(fu, "_qf_patched"):
        return # guard: do not patch twice
    _orig = fu.get_url
    def _custom_get_url(path=None, full_address=False):
        url = _orig(path, full_address)
        prefix = frappe.conf.get("custom_url_prefix", "")
        return prefix + url if prefix else url
    fu.get_url = _custom_get_url
    fu._qf_patched = True