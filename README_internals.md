# QuickFix Internal Notes

---

# Part 1: Request Handling & API

## Tracing a Request End-to-End

### Method API: `/api/method/quickfix.api.get_job_summary`
- This is handled by Frappe's method dispatch path for API methods.
- Frappe parses the URL after `/api/method/` as a dotted Python path, imports `quickfix.api`, and calls `get_job_summary` through `execute_cmd`.
- That means the request is handled by the Python function named `get_job_summary` inside `apps/quickfix/quickfix/api.py`.

### Resource API: `/api/resource/Job Card/JC-2024-0001`
- This goes through Frappe's REST resource handler rather than the method dispatcher.
- The resource API uses DocType metadata to read the document, apply read permissions, and return fields.
- Unlike `/api/method/`, it does not call a custom server method; it uses the generic resource controller that is aware of DocType permissions and field visibility.

### Website Routing: `/track-job`
- This is website routing, not an API route.
- Frappe resolves it through the website router and page render pipeline (`frappe.website.router`, `frappe.www.render`), or by matching a `www/` page or app-defined route.
- The request is handled by the website rendering system instead of the `/api` request handler.

### Session Management & CSRF Protection
- The `X-Frappe-CSRF-Token` header comes from the client-side `frappe.csrf_token` value.
- Frappe stores the token in `frappe.session.data.csrf_token` for the current user session.
- If the token is omitted or incorrect during a state-changing request, Frappe rejects the request with a CSRF validation error.
- In bench console, `import frappe; frappe.session.data` usually returns `{}` because that interactive session is not attached to a real browser session. It only contains extra session values when a web session is initialized.

### Error Visibility & Developer Mode
- With `developer_mode: 1`, Frappe returns full Python tracebacks and debugging details in the browser for exceptions in whitelisted methods.
- With `developer_mode: 0`, Frappe hides internal details and returns a generic error response so sensitive implementation data is not exposed.
- In production, hidden errors are logged to Frappe's error logging system, typically via `frappe.log_error` and into the site's error log / `error_log` table.

### Permission Checks

---

# Part 2: Database & ORM

## Database Internals
- Calling `frappe.get_doc("Job Card", name)` without `ignore_permissions` triggers permission checks in Frappe's document loading layer.
- If a `QF Technician` user is not assigned to that job, Frappe raises `frappe.PermissionError` before returning the document.
- The permission denial happens at the permission-check layer inside `get_doc`, so the request is stopped before normal business logic runs.

### Table Naming Conventions
- A query like `frappe.db.sql("SHOW TABLES LIKE '%Job%'")` returns names such as `tabJob Card`, `tabScheduled Job Log`, and `tabScheduled Job Type`.
- Frappe prefixes DocType table names with `tab` to distinguish application-managed tables from arbitrary or legacy tables.
- This prevents collisions with reserved names like `user` and makes it clear the table is associated with a Frappe DocType.

### Column Structure & Metadata
- `DESCRIBE `tabJob Card`` returns columns including `name`, `creation`, `modified`, `docstatus`, and `owner`.
- These columns map directly to common DocType metadata and workflow fields.

### Query Builder & ORM
- The app already implements `get_overdue_jobs()` in `quickfix/api.py` using `frappe.qb.DocType("Job Card")`.
- It selects `name`, `customer_name`, `assigned_technician`, `creation`, filters `status` in (`Pending Diagnosis`, `In Repair`), and `creation < now - 7 days`, then orders by creation ascending.

### Transactions & Commit Behavior
- The app also implements `transfer_job(from_tech, to_tech)` using raw SQL inside a try/except.
- It calls `frappe.db.commit()` on success, and `frappe.db.rollback()` in the except block.
- When an exception occurs, it logs the traceback with `frappe.log_error()` before re-raising.

### DocStatus Lifecycle
- `docstatus` values are:
  - `0` = Draft
  - `1` = Submitted
  - `2` = Cancelled
- You generally cannot call `save()` on a submitted document unless the document is amended or explicitly allowed by custom logic.
- You cannot call `submit()` on a cancelled document; submission is only valid from draft.
- A `Document has been modified after you have opened it` error happens when the saved `modified` timestamp in the database differs from the copy held by the form.
- Frappe prevents this by comparing timestamps before saving and rejecting concurrent overwrites.

### Anti-Patterns & Common Mistakes

#### Don't: Save documents during validation

```python
def validate(self):
    self.total = sum(r.amount for r in self.items)
    self.save()  # ❌ WRONG
    other = frappe.get_doc("Spare part", self.part)
    other.stock_qty -= self.qty
    other.save()  # ❌ WRONG
```

**Problems:**
1. `self.save()` inside `validate()` causes recursive save/on_update loops
2. Saving other documents during validation breaks separation of concerns
3. Validation should only verify state, not persist changes
#### Do: Use appropriate lifecycle hooks

```python
def validate(self):
    self.total = sum(r.amount for r in self.items)  # ✓ Validation only

def before_submit(self):
    # ✓ Persistence happens here, after validation passes
    other = frappe.get_doc("Spare part", self.part)
    other.stock_qty -= self.qty
    other.save()
```

---

# Part 3: DocType Internals

## Child Table Management
- When you append a row to `Job Card.parts_used` and save, Frappe automatically sets child row fields: `parent`, `parentfield`, `parenttype`, and `idx`.
- The database table name for `Part Usage Entry` is `tabPart Usage Entry`.
- If you delete the row at `idx=2` and resave, Frappe renumbers remaining rows so `idx` values remain sequential.

## Renaming & Link Integrity
- Renaming a `Technician` document with `frappe.rename_doc("Technician", old_name, new_name, merge=False)` updates linked fields such as `assigned_technician` on existing `Job Card` records automatically.
- This happens because `rename_doc()` updates links in the database as part of the rename operation.
- `Track Changes` means Frappe records revisions of the document when fields are changed, so you can see the history of edits.
- A field set as `unique` in the DocType creates a database-level unique constraint.
- A `frappe.db.exists()` check in `validate()` is only an application-level check and can still race unless the underlying DB constraint prevents duplicates.

---

# Part 4: Permissions & Security

## Permission Query & Visibility Control
- `permission_query_conditions` should limit `Job Card` list queries for `QF Technician` users to only those where `assigned_technician.user == frappe.session.user`.
- `has_permission` for `Service Invoice` should reject access for non-managers when the linked Job Card's `payment_status` is not `Paid`.
- The unsafe version of a whitelisted method returns data from `frappe.get_all` because `get_all` bypasses permission checks and can leak records or fields.
- The safe version uses `frappe.get_list` (permission-aware) and strips `customer_phone` and `customer_email` for non-manager users.
- Using `frappe.get_all` in a guest or low-privilege method is dangerous because it can bypass role-based permissions and return sensitive rows the caller should not see.

---

# Part 5: Document Lifecycle & Validation

## Lifecycle Hooks vs Class Override

Prefer `doc_events` for most custom validation and lifecycle changes instead of `override_doctype_class`.
**`doc_events` (Recommended):**
- Attach behavior to existing DocType controller without replacing it
- Preserves Frappe core and app controller inheritance
- Avoids MRO (Method Resolution Order) problems
- Reduces risk of missing `super()` calls

**`override_doctype_class` (Advanced):**
- Completely swaps the DocType controller class
- Use only when you need full custom controller implementation
- More invasive and harder to maintain
## Job Card Validation Rules

- `validate()` should verify that `customer_phone` is exactly 10 digits
- If status is `In Repair` or later, `assigned_technician` must exist
- Each `Part Usage Entry` row must compute `total_price = quantity * unit_price`
- `parts_total` is the sum of row `total_price` values
- `labour_charge` should be loaded from `Quickfix Settings` if not already set
- `final_amount` is `parts_total + labour_charge`
## Job Card Lifecycle Hooks

### `before_submit()`
- Only allow submission when status is `Ready for Delivery`
- Validate stock availability for each part

### `on_submit()`
- Deduct stock for each part
- Create `Service Invoice` with `insert(ignore_permissions=True)` (system-initiated write)
- Publish realtime event via `frappe.publish_realtime("job_ready", ...)`
- Enqueue `send_job_ready_email` (non-blocking, prevents email delays)

### `on_cancel()`
- Set status to `Cancelled`
- Restore part stock
- Cancel linked `Service Invoice` if exists

### `on_trash()`
- Prevent deletion unless document is Draft or Cancelled

### `on_update()`
- **Never** call `self.save()` — causes recursive loops
- Use helper methods like `recalculate_amounts()` instead

## Autoname & Document Renaming

- `autoname()` for `Spare part` should uppercase `part_code` then use naming series
- `rename_doc(..., merge=False)` — safe for updating links
- `rename_doc(..., merge=True)` — **dangerous**, can merge distinct records and lose data

---

# Part 6: Frontend & Assets

## Asset Includes

| Hook | Scope | Use Case |
|------|-------|----------|
| `app_include_js` | Desk only (logged-in) | Backend UI customization |
| `web_include_js` | Website/Portal (public) | Public features & Web Forms |

## DocType UI Customization

### `doctype_js`
- Customizes form view behavior (validation, field logic, actions)
- Enhances Job Card usability in Desk

### `doctype_list_js`
- Customizes list view (indicators, filters, list actions)
- Enhances Job Card list rendering

### `doctype_tree_js`
- Used for hierarchical DocTypes (not applicable to QuickFix)
- Example: Account, Warehouse, Item Group

## Build Process & Cache Busting

```bash
bench build --app quickfix
```

- Bundles and prepares JS/CSS assets
- Generates versioned (hashed) filenames
- Prevents browser caching of old assets
- Ensures latest frontend changes are loaded

## Templating: Print Formats vs Web Pages

### Print Format (Jinja)

**Automatically available:**
- `doc` — current document instance
- `meta` — DocType metadata
- `frappe` — Frappe object

**Used for:**
- PDF generation
- Print views

### Web Page (Jinja)

**NOT automatically available:**
- Data must be passed from backend context
- Or fetched using Jinja methods/APIs

**Used for:**
- Public-facing pages
- Portal views
---

# Part 7: Extension Patterns

## Override Strategies: Safe vs Unsafe Methods

### ✓ RECOMMENDED: `override_whitelisted_methods` (Hook-based)

```python
# hooks.py
override_whitelisted_methods = {
    "frappe.client.get_count": "quickfix.quickfix.overrides.get_counts"
}
```

- **Characteristics:**
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

### ❌ AVOID: Monkey Patching (Import-time)

```python
# somewhere in your app startup
import frappe.client
frappe.client.get_count = my_custom_function
```

---

**Characteristics:**
- Declared at import time — affects entire process
- Invisible — no central place to see all patches
- Brittle — breaks if Frappe changes internals
- Irreversible — original gone for entire process
- Dangerous — affects ALL apps in same bench
- Hard to debug — no trace of the swap

**When to use (if ever):**
- Almost never in production
- Emergency hotfixes only
- Isolated test environments only
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

## Conflict Resolution: Multiple Overrides

### What happens when two apps override the same method

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

Frappe processes hooks in **app installation order**. The LAST registered override WINS, silently replacing all previous ones.

**Result:**
```
App A's override is SILENTLY IGNORED ❌
```

**Consequences:**
- App A's logic stops working without error
- No warning or exception thrown
- Very hard to debug
- App A developer unaware of the override replacement

**Solution — Chain the Overrides**

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

---

## Function Signature Mismatch & TypeErrors

### Understanding Signature Mismatch

When your override function does NOT have the same parameters as the original function.

**Original function signature:**
```python
# frappe/client.py
def get_count(doctype, filters=None, debug=False, cache=False):
    pass
```

### TypeError Cases

#### Case 1: Missing Parameter
```python
# your override — missing cache parameter
def get_counts(doctype, filters=None, debug=False):
    pass

# caller does this
get_count("Customer", filters=None, debug=False, cache=True)
#                                                ↑
# TypeError: get_counts() got unexpected keyword argument 'cache'
```

#### Case 2: Wrong Parameter Name
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

#### Case 3: Extra Required Parameter
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

#### Case 4: Wrong Argument Order
```python
# your override — wrong order
def get_counts(filters=None, doctype, debug=False, cache=False):
    #           ↑ default before non-default
    pass

# SyntaxError at definition time — not even TypeError
# SyntaxError: non-default argument follows default argument
```

### TypeError Reference

| Situation | Error |
|-----------|-------|
| Missing parameter | `TypeError: unexpected keyword argument` |
| Wrong parameter name | `TypeError: unexpected keyword argument` |
| Extra required parameter | `TypeError: missing required argument` |
| Caller passes positional args, override expects keyword | `TypeError: takes N positional arguments` |

### Safe Pattern: Always Match Signatures Exactly

**Step 1: Check original signature**
```python
import inspect
from frappe.client import get_count
print(inspect.signature(get_count))
# Output: (doctype, filters=None, debug=False, cache=False)
```

**Step 2: Match it exactly**
```python
def get_counts(doctype, filters=None, debug=False, cache=False):
    pass  # ✓ Exact match
```

**Step 3: Or use `**kwargs` as safety net**
```python
def get_counts(doctype, filters=None, debug=False, cache=False, **kwargs):
    # ✓ Catches any extra future params
    pass
```

---

## Field Name Collisions

**Risk:** Your field name matches a future Frappe field

**Result:** Migration crash, data corruption, or silent overwrite

**Fix:** Always prefix field names with app name
```
qf_status     # ✓ Safe
qf_priority   # ✓ Safe
status        # ❌ Collision risk
priority      # ❌ Collision risk
```

---

# Part 8: Patching & Deployment

## Patch Architecture

### The `_qf_patched` Guard

A boolean flag set on a function to prevent the same patch being applied more than once.

**Without it:**
- **Double patch:** Each restart applies patch again, doubling side effects
- **Infinite recursion:** Patched function calls itself, crashes on RecursionError
- **Memory leak:** Each restart wraps previous patch, chain grows unbounded

### Where to Put Patches

**❌ DON'T: Put patches in `__init__.py`**
- Runs at import time — Frappe may not be ready
- Invisible — no central inventory
- Hard to disable or audit
- Breaks test isolation (auto-applies on import)

**✓ DO: Use dedicated `monkey_patches.py`**
- Single file — complete inventory
- Called explicitly from boot hook (not import time)
- Easy to find, review, audit, disable
- Skippable in test environments
- Each patch independently guarded

## Patch Escalation Path

Always use the minimum power needed. Each level adds more risk and less reversibility.

---

### Level 1: `doc_events` (Always Try First)

**What it does:**
- Hooks into document lifecycle from outside
- Does not touch original class

**Advantages:**
- Zero risk to original behavior
- Multiple apps can hook same event safely
- Fully reversible on uninstall
- Official Frappe pattern

**Use when:**
- Reacting to save/submit/cancel
- Adding emails, logs, or side effects

**Cannot:**
- Change existing method behavior
- Intercept non-lifecycle events

---

### Level 2: `override_doctype_class`

**What it does:**
- Replaces DocType controller via class inheritance
- Original preserved through `super()`

**Advantages:**
- Full access to all self properties and methods
- Can override any method or add new ones
- Original never deleted, just extended
- Reversible on uninstall

**Use when:**
- Need to change how an existing method works
- Need full class-level control

**Cannot** work outside DocType controllers.
Only one app can override same class safely.

### Level 3 — override_whitelisted_methods

Replaces a whitelisted API function via hooks.py.
Explicit and visible — not hidden at import time.

- Declared in hooks.py — easy to find
- Reversible on uninstall
- No import-time side effects

**Use when** overriding a whitelisted API endpoint
that doc_events and class override cannot reach.

**Cannot** override non-whitelisted functions.
Must match original signature exactly.

### Level 4 — Monkey Patch (Last Resort Only)

Directly replaces any Python function at runtime.

- Invisible — not declared anywhere central
- Brittle — breaks if Frappe renames function
- Irreversible — affects entire Python process
- Dangerous — affects all apps in same bench
- No official Frappe support

**Use only when** levels 1/2/3 genuinely cannot
solve the problem. Always document WHY in code.
Always use guard flag. Always store original.

## Why frappe.call inside validate is unreliable

`validate` is part of the synchronous document save flow, but `frappe.call`
is asynchronous.

When `frappe.call` is used inside `validate`, the save operation continues
before the server response returns. This means the document may already be
saved before validation logic inside the callback executes.

Because of this, async validations should not be performed inside `validate`.

Recommended approaches:
- Use server-side Python validation
- Fetch async data earlier using `onload` or `refresh`
- Use cached/preloaded data during validate
# Tree DocType — Internals Guide

## What is a Tree DocType

A DocType that stores records in a parent-child
hierarchy instead of a flat list. Each record can
be a parent of others, forming a tree structure.

---

## Real World Examples

```
Employee Hierarchy
├── CEO
│   ├── CTO
│   │   ├── Senior Developer
│   │   └── Junior Developer
│   └── CFO
```

## Required Fields

### parent_field
Stores the name of the parent record.
Links this record upward in the tree.
Field type is Link pointing to the same DocType.

### is_group
Boolean marking whether this node is a
branch (can have children) or leaf (cannot).

```
is_group = 1 → branch → folder icon → expandable
             → cannot store transactions

is_group = 0 → leaf → file icon → no children
             → stores actual transactions
```

### lft and rgt
Integer fields managed automatically by Frappe.
Used internally for efficient tree traversal.
Never set manually.

### old_parent
Tracks the previous parent when a node is moved.
Used for cleanup during restructuring.

## DocType Settings

Two settings must be enabled in the DocType form:

- **Is Tree** — marks this as a tree DocType
- **Tree Parent Field** — specifies which field
  holds the parent reference

## What doctype_tree_js Does

A hooks.py entry that loads custom JavaScript
specifically for the Tree View page of a DocType.

Tree View is a separate page that renders the
hierarchy visually — different from list view
and form view.

Used to add toolbar buttons, node click handlers,
custom filters, breadcrumbs, and tree-level logic
that only applies when viewing the tree structure.

Registered in hooks.py under `doctype_tree_js`
and only loads on the tree page — not on the form.

## is_group Behavior

When user tries to post a transaction under
a group node, Frappe blocks it automatically.
Transactions are only allowed on leaf nodes.

Tree view shows group nodes as expandable folders
and leaf nodes as non-expandable file items.

## lft rgt — Nested Set Model

Frappe uses Nested Set Model for tree storage.
Each node gets left and right numbers encoding
its position in the entire tree.

This allows fetching all descendants of any node
in a single SQL query without recursion.
Frappe recalculates these automatically on
insert, move, and delete operations.

## Summary

| Field | Purpose |
|---|---|
| `parent_field` | Points to parent node |
| `is_group` | Branch or leaf flag |
| `lft / rgt` | Auto-managed traversal values |
| `old_parent` | Previous parent tracking |

```
doctype_tree_js  → JS for Tree View page only
doctype_js       → JS for Form View page only
doctype_list_js  → JS for List View page only
```

# Client Script vs Shipped JS

## Client Script DocType

Used mainly by consultants/admins for quick UI customizations directly from Desk without changing app code.

**Advantages:**
- Fast customization
- No deployment needed
- Easy for non-developers

**Risks in production:**
- Hard to version control
- Can break after updates
- Difficult to debug
- Logic scattered across sites

## Shipped JS (doctype_js / job_card.js)

Used by app developers inside the app source code.

**Advantages:**
- Version controlled
- Tested and maintainable
- Easier deployment
- Better for team development

**Tradeoff:**
- Requires build/restart/deployment process

# JS Hide vs Real Security

Example:

```javascript
if (!frappe.user.has_role("Manager")) {
    frm.set_df_property(
        "customer_phone",
        "hidden",
        1
    );
}
```

This only hides the field in the UI. The data still exists on the server and can still be fetched using API calls.

Example:

```javascript
frappe.db.get_value(
    "Job Card",
    "JOB-0001",
    "customer_phone"
)
```

**Reason:**

- Client-side JS only changes the interface
- It does NOT enforce backend permissions
## Frappe Query Report — f-string vs Parameterized

Your query already uses the **safe parameterized pattern** `%(key)s` — here's what that means:

### Your Query (Safe)
```sql
WHERE
    status NOT IN ('Delivered', 'Cancelled') AND
    (%(device_type)s IS NULL OR device_type = %(device_type)s)
```

```python
def execute(filters):
    return frappe.db.sql("""
        SELECT name, customer_name, device_type, status,
               assigned_technician, estimate_cost, creation
        FROM `tabJob Card`
        WHERE status NOT IN ('Delivered', 'Cancelled')
          AND (%(device_type)s IS NULL OR device_type = %(device_type)s)
        ORDER BY creation DESC
    """, filters, as_dict=1)
```

- `%(device_type)s` → Frappe pulls the value from `filters` dict safely
- If filter is empty/None → `%(device_type)s IS NULL` returns all rows (no filter applied)
- If filter has a value → `device_type = %(device_type)s` filters by it

### The Wrong Way (f-string)
```python
def execute(filters):
    device_type = filters.get("device_type")
    return frappe.db.sql(f"""
        SELECT * FROM `tabJob Card`
        WHERE device_type = '{device_type}'
    """)
```
→ If someone passes `' OR '1'='1` as filter value, query breaks or leaks data.

### Key Points

|                        | f-string                 | `%(key)s`             |
|       ---              |      ---                 |      ---              |
| Input handling         | Injected into string     | Passed separately     |
| Optional filter (None) | Needs manual `if` checks | Handled inline in SQL |
| SQL Injection safe     |  No                      | Yes                   |

> **Your pattern** `(%(device_type)s IS NULL OR device_type = %(device_type)s)` is the **recommended Frappe way** to handle optional filters cleanly in a single query.
# Prepared Report vs Real-Time Script Report

## When to Use Each

| Situation | Use |
|---|---|
| Live stock / job status | Real-Time Script Report |
| Monthly summary / P&L | Prepared Report |
| Data changes frequently | Real-Time |
| Report is slow (> 5 sec) | Prepared |
| Shared as management snapshot | Prepared |
| Live operational decisions | Real-Time |

---

## The Staleness Problem

```
9:00 AM  → Prepared Report generated → 3 parts below reorder
9:30 AM  → Technician uses 10 units of Part X (stock drops)
10:00 AM → Manager opens same report → still sees old data ❌
```
**User sees stale data → makes wrong decisions.**

---

## Caching Risk — What the User Sees

| Event | Real-Time | Prepared |
|---|---|---|
| Part stock changes | Updates instantly ✅ | Shows old stock ❌ |
| New part added | Appears immediately ✅ | Missing from report ❌ |
| Price updated | Reflects on refresh ✅ | Old price shown ❌ |

> **Silent risk** — no error, no warning. Just wrong data.

---

## Staleness Risk by Report Type

| Report | Risk | Reason |
|---|---|---|
| Spare Parts Stock |  High | Stock changes per job |
| Job Card Status |  High | Status changes hourly |
| Monthly Revenue |  Low | Historical, frozen data |
| Weekly Technician Summary |  Medium | Changes daily, reviewed weekly |

---

## How to Reduce Staleness Risk

**1. Show generation timestamp in summary**

**2. Schedule auto re-generation via hooks.py**

---
# Report Builder vs Script Report

## What is Report Builder?

Report Builder is a no-code reporting tool in Frappe used to quickly generate reports directly from a DocType without writing Python or SQL.

It allows users to:
- select columns
- apply filters
- group data
- sort records
- export results

Report Builder is appropriate for:
- simple listing reports
- operational views
- basic filtering and searching
- non-technical users

Example:
- Open Job Cards list
- Customer History report
- Spare Parts stock list

Limitations:
- no custom backend logic
- no dynamic columns
- limited calculations
- limited analytics support


---

# What is Script Report?

Script Report is an advanced reporting system where developers write Python code to generate report data.

It is used when:
- complex calculations are needed
- dynamic columns are required
- charts and summaries are needed
- multiple DocTypes are involved
- custom business logic is required

Script Reports provide:
- full Python control
- dynamic report generation
- charts
- report_summary
- conditional formatting
- scalable analytics

Example:
- Technician Performance Report
- Revenue Analytics
- Inventory Valuation Report


---

# When Report Builder Becomes a Mistake in Production

Using Report Builder in production becomes a mistake when the report requires:
- heavy calculations
- dynamic columns
- analytics
- KPI summaries
- advanced filtering logic
- optimized queries

In such scenarios:
- performance may become poor
- customization becomes difficult
- calculations may be inaccurate
- maintenance becomes harder

A Script Report should be used instead because it provides proper backend control, optimized queries, and scalable business logic.