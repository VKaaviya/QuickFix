# QuickFix Internal Notes

## B1 - Trace a Request End-to-End

### 1. `/api/method/quickfix.api.get_job_summary`
- This is handled by Frappe's method dispatch path for API methods.
- Frappe parses the URL after `/api/method/` as a dotted Python path, imports `quickfix.api`, and calls `get_job_summary` through `execute_cmd`.
- That means the request is handled by the Python function named `get_job_summary` inside `apps/quickfix/quickfix/api.py`.

### 2. `/api/resource/Job Card/JC-2024-0001`
- This goes through Frappe's REST resource handler rather than the method dispatcher.
- The resource API uses DocType metadata to read the document, apply read permissions, and return fields.
- Unlike `/api/method/`, it does not call a custom server method; it uses the generic resource controller that is aware of DocType permissions and field visibility.

### 3. `/track-job`
- This is website routing, not an API route.
- Frappe resolves it through the website router and page render pipeline (`frappe.website.router`, `frappe.www.render`), or by matching a `www/` page or app-defined route.
- The request is handled by the website rendering system instead of the `/api` request handler.

### Session & CSRF
- The `X-Frappe-CSRF-Token` header comes from the client-side `frappe.csrf_token` value.
- Frappe stores the token in `frappe.session.data.csrf_token` for the current user session.
- If the token is omitted or incorrect during a state-changing request, Frappe rejects the request with a CSRF validation error.
- In bench console, `import frappe; frappe.session.data` usually returns `{}` because that interactive session is not attached to a real browser session. It only contains extra session values when a web session is initialized.

### Error visibility
- With `developer_mode: 1`, Frappe returns full Python tracebacks and debugging details in the browser for exceptions in whitelisted methods.
- With `developer_mode: 0`, Frappe hides internal details and returns a generic error response so sensitive implementation data is not exposed.
- In production, hidden errors are logged to Frappe's error logging system, typically via `frappe.log_error` and into the site's error log / `error_log` table.

### Permission check location
- Calling `frappe.get_doc("Job Card", name)` without `ignore_permissions` triggers permission checks in Frappe's document loading layer.
- If a `QF Technician` user is not assigned to that job, Frappe raises `frappe.PermissionError` before returning the document.
- The permission denial happens at the permission-check layer inside `get_doc`, so the request is stopped before normal business logic runs.

## B2 - ORM Internals & Query Builder

### A. Table naming
- A query like `frappe.db.sql("SHOW TABLES LIKE '%Job%'")` returns names such as `tabJob Card`, `tabScheduled Job Log`, and `tabScheduled Job Type`.
- Frappe prefixes DocType table names with `tab` to distinguish application-managed tables from arbitrary or legacy tables.
- This prevents collisions with reserved names like `user` and makes it clear the table is associated with a Frappe DocType.

### B. Describe table columns
- `DESCRIBE `tabJob Card`` returns columns including `name`, `creation`, `modified`, `docstatus`, and `owner`.
- These columns map directly to common DocType metadata and workflow fields.

### C. Query Builder in code
- The app already implements `get_overdue_jobs()` in `quickfix/api.py` using `frappe.qb.DocType("Job Card")`.
- It selects `name`, `customer_name`, `assigned_technician`, `creation`, filters `status` in (`Pending Diagnosis`, `In Repair`), and `creation < now - 7 days`, then orders by creation ascending.

### D. Transactions & commit behavior
- The app also implements `transfer_job(from_tech, to_tech)` using raw SQL inside a try/except.
- It calls `frappe.db.commit()` on success, and `frappe.db.rollback()` in the except block.
- When an exception occurs, it logs the traceback with `frappe.log_error()` before re-raising.

### E. DocStatus transitions
- `docstatus` values are:
  - `0` = Draft
  - `1` = Submitted
  - `2` = Cancelled
- You generally cannot call `save()` on a submitted document unless the document is amended or explicitly allowed by custom logic.
- You cannot call `submit()` on a cancelled document; submission is only valid from draft.
- A `Document has been modified after you have opened it` error happens when the saved `modified` timestamp in the database differs from the copy held by the form.
- Frappe prevents this by comparing timestamps before saving and rejecting concurrent overwrites.

### F. Dangerous patterns
- The original buggy pattern was:
  ```python
  def validate(self):
      self.total = sum(r.amount for r in self.items)
      self.save()
      other = frappe.get_doc("Spare part", self.part)
      other.stock_qty -= self.qty
      other.save()
  ```
- Bugs:
  1. `self.save()` inside `validate()` causes recursive save/on_update loops.
  2. Saving another document inside `validate()` is unsafe because validation should not perform external persistence side effects.
- Corrected version:
  ```python
  def validate(self):
      self.total = sum(r.amount for r in self.items)

  def before_submit(self):
      other = frappe.get_doc("Spare part", self.part)
      other.stock_qty -= self.qty
      other.save()
  ```

## C1 - Child Table Internals
- When you append a row to `Job Card.parts_used` and save, Frappe automatically sets child row fields: `parent`, `parentfield`, `parenttype`, and `idx`.
- The database table name for `Part Usage Entry` is `tabPart Usage Entry`.
- If you delete the row at `idx=2` and resave, Frappe renumbers remaining rows so `idx` values remain sequential.

## C2 - Renaming and link integrity
- Renaming a `Technician` document with `frappe.rename_doc("Technician", old_name, new_name, merge=False)` updates linked fields such as `assigned_technician` on existing `Job Card` records automatically.
- This happens because `rename_doc()` updates links in the database as part of the rename operation.
- `Track Changes` means Frappe records revisions of the document when fields are changed, so you can see the history of edits.
- A field set as `unique` in the DocType creates a database-level unique constraint.
- A `frappe.db.exists()` check in `validate()` is only an application-level check and can still race unless the underlying DB constraint prevents duplicates.

## D2 - Permission Query & has_permission
- `permission_query_conditions` should limit `Job Card` list queries for `QF Technician` users to only those where `assigned_technician.user == frappe.session.user`.
- `has_permission` for `Service Invoice` should reject access for non-managers when the linked Job Card's `payment_status` is not `Paid`.
- The unsafe version of a whitelisted method returns data from `frappe.get_all` because `get_all` bypasses permission checks and can leak records or fields.
- The safe version uses `frappe.get_list` (permission-aware) and strips `customer_phone` and `customer_email` for non-manager users.
- Using `frappe.get_all` in a guest or low-privilege method is dangerous because it can bypass role-based permissions and return sensitive rows the caller should not see.

## E1 / E2 - Lifecycle hooks and autoname
- Prefer `doc_events` for most custom validation and lifecycle changes instead of `override_doctype_class`.
  - `doc_events` hooks attach behavior to the existing DocType controller without replacing the class.
  - This is safer because it preserves Frappe core and app controller inheritance, avoids MRO problems, and reduces the chance of missing a future `super()` call or breaking built-in behavior.
  - `override_doctype_class` is more invasive: it completely swaps the DocType controller class, which is useful only when you need a full custom controller implementation.
- `validate()` should verify that `customer_phone` is exactly 10 digits.
- If status is `In Repair` or later, `assigned_technician` must exist.
- Each `Part Usage Entry` row must compute `total_price = quandity * unit_price`.
- `parts_total` is the sum of row `total_price` values.
- `labour_charge` should be loaded from `Quickfix Settings` if not already set.
- `final_amountc` is `parts_total + labour_charge`.
- `before_submit()` must only allow submission when status is `Ready for Delivery` and must validate stock availability per part.
- `on_submit()` should:
  - deduct stock for each part,
  - create a `Service Invoice` with `insert(ignore_permissions=True)` because this is a system-initiated internal write,
  - publish realtime via `frappe.publish_realtime("job_ready", ...)`,
  - enqueue `send_job_ready_email` so the submit flow is not blocked by email delivery.
- `on_cancel()` should set status to `Cancelled`, restore part stock, and cancel the linked `Service Invoice` if one exists.
- `on_trash()` should prevent deletion unless the document is Draft or Cancelled.
- `on_update()` must not call `self.save()` because that causes recursive saves. Instead, use helper methods such as `recalculate_amounts()`.
- `autoname()` for `Spare part` should uppercase `part_code` and then use the naming series.
- `rename_doc(..., merge=False)` is safe for updating links, while `merge=True` is dangerous because it can merge two distinct records and lose data.

## Asset Hooks: app_include_js vs web_include_js
- app_include_js loads JS only in Desk (logged-in users)
- web_include_js loads JS only in Website/Portal (guest + public users)
- Use app_include_js for backend UI customization
- Use web_include_js for public-facing features and Web Forms
## DocType UI Customization: doctype_js & doctype_list_js (Job Card)
-  doctype_js customizes form view behavior (validation, field logic, actions)
- doctype_list_js customizes list view (indicators, filters, list actions)
- Both used to enhance Job Card usability in Desk
## Tree View Concept: doctype_tree_js
- Not applicable for current DocTypes
- Used for hierarchical data structures (parent-child relationship)
- Example DocTypes: Account, Warehouse, Item Group
- Helps visualize nested data in tree format
## Build Process & Cache Busting
- bench build --app quickfix bundles and prepares JS/CSS assets
- Generates versioned (hashed) files to avoid browser caching issues
- Ensures latest frontend changes are loaded after updates
- Prevents stale UI caused by cached old assets

## Jinja Context: Print Formats vs Web Pages
# Print Format Context
Automatically receives:
doc (current document)
meta, frappe, and other system variables
Strongly tied to a specific DocType record
Used for generating PDFs/print views
# Web Page Context
Does NOT automatically include doc
Data must be:
Passed manually from backend
Or fetched using Jinja methods / APIs
Used for public-facing pages
# Quickfix Internals — Override Strategies

## override_whitelisted_methods vs Monkey Patching

### override_whitelisted_methods (Hook-based)

```python
# hooks.py
override_whitelisted_methods = {
    "frappe.client.get_count": "quickfix.quickfix.overrides.get_counts"
}
```

**Characteristics:**
- Declared explicitly in hooks.py
- Frappe manages the swap at startup
- Reversible — uninstalling app restores original
- Visible — anyone reading hooks.py knows about it
- Safe — only affects whitelisted API endpoints
- Follows Frappe's intended extension pattern

**When to use:**
- Overriding API endpoints called from browser
- Adding logging/audit to existing Frappe APIs
- Extending standard Frappe behavior in your app
- When you need clean, maintainable customization

---

### Monkey Patching (Import-time)

```python
# somewhere in your app startup
import frappe.client
frappe.client.get_count = my_custom_function
```

**Characteristics:**
- Happens at import time — affects entire process
- Invisible — no central place to see all patches
- Brittle — breaks if Frappe changes internals
- Irreversible — original gone for entire process
- Dangerous — affects ALL apps in same bench
- Hard to debug — no trace of the swap

**When to use:**
- Almost never in production
- Only for emergency hotfixes
- Only in isolated test environments
- Never in shared multi-app benches

---

### Side by Side Comparison

| Aspect | override_whitelisted_methods | Monkey Patching |
|---|---|---|
| Visibility | Explicit in hooks.py | Hidden at import |
| Reversible | Yes — uninstall app | No — process-wide |
| Scope | API endpoint only | Entire process |
| Safety | High | Low |
| Debuggability | Easy | Very Hard |
| Frappe support | Official | Unofficial |
| Multi-app safe | Yes | Dangerous |

---

## What Happens if TWO Apps Both Register Same Method

```python
# App A hooks.py
override_whitelisted_methods = {
    "frappe.client.get_count": "app_a.overrides.get_count"
}

# App B hooks.py
override_whitelisted_methods = {
    "frappe.client.get_count": "app_b.overrides.get_count"
}
```

### What Frappe Does:

Frappe processes hooks in **app installation order**.
The LAST registered override WINS and replaces all previous ones.

```
Frappe starts
      │
      ▼
Loads App A hooks → registers app_a.overrides.get_count
      │
      ▼
Loads App B hooks → registers app_b.overrides.get_count
      │             OVERWRITES App A's override
      ▼
Final result: only App B's override is active
App A's override is SILENTLY IGNORED ❌
```

### Consequences:
- App A's audit logging stops working silently
- No error or warning is thrown
- Very hard to debug
- App A developer has no idea their override was replaced

### Solution — Chain the Overrides:

```python
# App B should call App A's override
# not the original function

import frappe
from app_a.overrides import get_count as app_a_get_count

def get_count(doctype, filters=None, debug=False, cache=False):
    # call App A's override first
    result = app_a_get_count(
        doctype,
        filters = filters,
        debug   = debug,
        cache   = cache
    )
    # then do App B's logic
    my_extra_logic()
    return result
```

---

## Signature Mismatch — TypeError Explained

### What is Signature Mismatch

When your override function does NOT have
the same parameters as the original function.

### Original signature:
```python
# frappe/client.py
def get_count(doctype, filters=None, debug=False, cache=False):
    pass
```

### Mismatch examples and when TypeError occurs:

#### Case 1 — Missing Parameter
```python
# your override — missing cache parameter
def get_counts(doctype, filters=None, debug=False):
    pass

# caller does this
get_count("Customer", filters=None, debug=False, cache=True)
#                                                ↑
# TypeError: get_counts() got unexpected keyword argument 'cache'
```

#### Case 2 — Wrong Parameter Name
```python
# your override — wrong name
def get_counts(doctype, filter=None, debug=False, cache=False):
    #                   ↑ should be filters not filter
    pass

# caller does this
get_count("Customer", filters={"status": "Active"})
#                     ↑
# TypeError: get_counts() got unexpected keyword argument 'filters'
```

#### Case 3 — Extra Required Parameter
```python
# your override — added required param with no default
def get_counts(doctype, filters=None, debug=False, cache=False, user):
    #                                                            ↑
    # required param — no default value
    pass

# caller does this
get_count("Customer")
# TypeError: get_counts() missing required argument 'user'
```

#### Case 4 — Wrong Argument Order
```python
# your override — wrong order
def get_counts(filters=None, doctype, debug=False, cache=False):
    #           ↑ default before non-default
    pass

# SyntaxError at definition time — not even TypeError
# SyntaxError: non-default argument follows default argument
```

### When You Get TypeError Summary:

```
Situation                              Error
──────────────────────────────────────────────────────
Missing parameter in override          TypeError: unexpected keyword argument
Wrong parameter name                   TypeError: unexpected keyword argument
Extra required parameter               TypeError: missing required argument
Caller passes positional args          TypeError: takes N positional arguments
  but override expects keyword only
```

### Safe Pattern — Always Match Exactly:

```python
# Step 1 — check original signature
import inspect
from frappe.client import get_count
print(inspect.signature(get_count))
# (doctype, filters=None, debug=False, cache=False)

# Step 2 — match it exactly in your override
def get_counts(doctype, filters=None, debug=False, cache=False):
    #          ↑ exact same params, exact same defaults
    pass

# Step 3 — or use **kwargs as safety net
def get_counts(doctype, filters=None, debug=False, cache=False, **kwargs):
    #                                                            ↑ catches
    #                                                 any extra future params
    pass
```

## Fieldname Collision:
──────────────────────────────────────────
- Risk    : your field name = future Frappe field
- Result  : migration crash / data corruption /
          silent overwrite
- Fix     : always prefix fieldnames with app name
          qf_status not status
          qf_priority not priority

## Patching Order:
──────────────────────────────────────────
- Never merge patch1 (create field) +
       patch2 (read field) into one patch

- Because:
  insert Custom Field ≠ column in DB
  column only added during bench migrate
  which runs BETWEEN separate patch entries

- Separate patches guarantee:
  patch1 → creates Custom Field record
  migrate → adds actual DB column
  patch2 → safely reads that column 