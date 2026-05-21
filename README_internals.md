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

### Authentication Methods: Session Cookies vs. Tokens

#### Session Cookie Authentication
- **How it works**: The server creates a session on login and stores session data (user ID, permissions, etc.) server-side. A session ID is sent to the client as an HTTP cookie. Subsequent requests include this cookie, allowing the server to look up the session data.
- **State**: Stateful - the server maintains session state.
- **Storage**: Session data stored on server (often in Redis or database), client stores only the session ID cookie.
- **Expiration**: Typically expires when the browser closes or after a timeout period.
- **Security**: Relies on secure cookie attributes (HttpOnly, Secure, SameSite) and CSRF protection for state-changing requests.

#### Token Authentication (e.g., JWT, API Tokens)
- **How it works**: On login, the server issues a signed token containing user claims (ID, permissions, expiration). The client stores this token and sends it in request headers (usually `Authorization: Bearer <token>`). The server validates the token's signature and claims without storing session state.
- **State**: Stateless - all user information is encoded in the token.
- **Storage**: Token stored client-side (localStorage, sessionStorage, or secure storage), server doesn't store session data.
- **Expiration**: Token has built-in expiration, can be refreshed.
- **Security**: Token must be protected from theft; no automatic CSRF protection needed for stateless APIs.

#### Browser Use vs. Server-to-Server
- **Browser Use**: Session cookie authentication is more appropriate. Browsers automatically handle cookie sending with requests, and Frappe's CSRF protection works seamlessly with session-based auth. Cookies integrate well with browser security features and user experience (automatic login persistence).
- **Server-to-Server**: Token authentication is more appropriate. Tokens are self-contained and easier to manage in programmatic clients. No cookie handling needed, better for microservices, mobile apps, or third-party integrations where maintaining server-side session state is impractical.

### Error Visibility & Developer Mode
- With `developer_mode: 1`, Frappe returns full Python tracebacks and debugging details in the browser for exceptions in whitelisted methods.
- With `developer_mode: 0`, Frappe hides internal details and returns a generic error response so sensitive implementation data is not exposed.
- In production, hidden errors are logged to Frappe's error logging system, typically via `frappe.log_error` and into the site's error log / `error_log` table.

### Redis Cache
- `bootinfo` data for the current user and site settings
- DocType metadata / `meta` definitions
- website context and route/page settings
- translations for labels and messages
- user permissions and role access rules

### Stale UI Risk
If a dashboard chart caches query results and a Job Card status changes, the chart can keep showing old counts until the cache is invalidated. For example, after a Job Card switches from `In Repair` to `Completed`, a status-based summary chart may still display the previous `In Repair` total.

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

### Query patterns
- f-string:
```python
frappe.db.sql(f"SELECT * FROM `tabJob Card` WHERE customer_phone = '{phone}'")
```
- parameterized:
```python
frappe.db.sql(
    "SELECT * FROM `tabJob Card` WHERE customer_phone = %(phone)s",
    {"phone": phone},
)
```
- another pattern:
```python
frappe.db.sql(
    "SELECT * FROM `tabJob Card` WHERE status LIKE %(status)s",
    {"status": status + "%"},
)
```
- `frappe.db.escape(value)` exists, but parameterized queries are safer and preferred.

### Search Indexes & Over-Indexing
- Do not add a search index to every field by default. Indexes are useful only when a field is commonly used in filters, joins, sorting, unique checks, or lookups.
- Every index is an extra database structure that must be maintained whenever rows are inserted, updated, or deleted.
- Over-indexing makes writes slower because the database has to update the table data plus all matching indexes.
- It increases disk usage and memory pressure because indexes consume storage and compete for buffer/cache space.
- It can make query planning more expensive because the database optimizer has more possible indexes to evaluate.
- It can also slow schema changes and migrations, especially on large DocType tables.
- For QuickFix, good index candidates are fields frequently searched in list views or reports, such as `status`, `assigned_technician`, `creation`, or `delivery_date`. Poor candidates are rarely filtered long text fields, notes, descriptions, or fields with low query value.

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

- Raw printing sends direct ESC/POS commands to thermal printers for fast receipt printing without HTML or PDF rendering.  
- Frappe’s HTML-PDF printing uses Jinja templates + WeasyPrint to convert styled HTML/CSS into printable PDF documents.  
- Raw printing is lightweight and printer-specific, while WeasyPrint supports rich layouts, tables, images, and page styling.  
- CSS properties that often fail or behave differently in WeasyPrint: `position: sticky`, `backdrop-filter`, and complex `flexbox/grid` layouts.

## Background Jobs

### short queue

- Sending a single email notification
- Updating a cache entry
- Simple document hooks (on_submit lightweight actions)
- Auto-assignment rules
- Reminder notifications

## default queue

- Bulk email sending
- Report generation (Script Reports)
- Scheduled job triggers (daily, hourly tasks)
- Data import/export (small-medium files)
- Webhook delivery

## long queue

- Large data imports (thousands of rows)
- PDF generation for bulk print
- Full site backup
- Bulk update operations
- Database-heavy scheduled tasks

*short   queue  ──→  worker.short    (1 worker, fast turnaround)
default queue  ──→  worker.default  (1 worker, medium tasks)
long    queue  ──→  worker.long     (1 worker, heavy tasks)*

### Triggering & locating errors (minimal)
- Trigger: enqueue a job that raises an exception, e.g. `frappe.enqueue("quickfix.quickfix.M3.error_job")`.
- Find: `Setup → Error Log` records fields like: `seen`, `reference_doctype`, `reference_name`, `method`, `error`, `trace_id`, `metadata`, `_user_tags`, `_comments`, `_assign`, `liked_by`

- RQ dashboard: open failed job → click **Requeue** to retry (or use `rq requeue` CLI).

## Scheduler Per Site

To pause the scheduler for a specific site:

```bash
bench --site quickfix-dev.localhost scheduler pause
```

To enable it again:

```bash
bench --site quickfix-dev.localhost scheduler resume
```

- This is useful on a development site because scheduled jobs can send emails, create logs, trigger notifications, run reports, or modify test data while you are debugging. Pausing the scheduler keeps background automation from changing dev data unexpectedly.

- If the scheduler enqueues jobs while the worker is down, those jobs remain in the Redis queue. When the worker starts again, it picks up the queued jobs and runs them.

- If the scheduler itself is paused or stopped, missed schedule times are not usually backfilled automatically. The job runs again only at the next scheduled time after the scheduler is active.


## K3 N+1 query deduction 
```python
job_cards=frappe.get_all("Job Card",field=["name","assigned_technician"])
tech=[i.assigned_technician for i in job_cards]
technicians=frappe.get_all("Technician",fields=["technician_name","mobile_number"],filters=["name":["in",tech]])
for t in technicians:
    print(t.technician_name , t.mobile_number) 
```

## L1 A-
- req1:GET /api/resource/Job Card
    res : 
    ```json
    {"data":[{"name":"JC-2026-00001"},{"name":"JC-2026-00002"},{"name":"JC-2026-00001-1"},{"name":"JC-2026-00003"},{"name":"JC-2026-00002-1"},{"name":"JC-2026-00002-2"},{"name":"JC-2026-00004"},{"name":"JC-2026-00003-1"},{"name":"JC-2026-00005"},{"name":"JC-2026-00005-1"},{"name":"JC-2026-00006"},{"name":"JC-2026-00007"},{"name":"JC-2026-00008"},{"name":"JC-2026-00009"},{"name":"JC-2026-00009-1"},{"name":"JC-2026-00010"},{"name":"JC-2026-00010-1"},{"name":"JC-2026-00004-1"},{"name":"JC-2026-00011"}]}
    ```
- req2 : GET /api/resource/Job Card/JC-2026-00011
    res : 
    ```json
    {"data":{"name":"JC-2026-00011","owner":"Administrator","creation":"2026-05-13 16:33:17.190333","modified":"2026-05-13 16:33:23.005652","modified_by":"Administrator","docstatus":1,"idx":0,"customer_name":"kaviya","customer_phone":"1234567890","customer_email":"kaviyaveerapandi21@gmail.com","device_type":"Tablet","problem_description":"<div class=\"ql-editor read-mode\"><p>wertyuio</p></div>","assigned_technician":"new_TECH0003","estimate_cost":0.0,"priority":"Normal","parts_total":3000.0,"labour_charge":500.0,"final_amountc":3500.0,"payment_status":"Unpaid","status":"Ready for Delivery","doctype":"Job Card","parts_used":[{"name":"24kj0a6g8v","owner":"Administrator","creation":"2026-05-13 16:33:17.190333","modified":"2026-05-13 16:33:23.005652","modified_by":"Administrator","docstatus":1,"idx":1,"part":"PART-2026-0002","part_name":"Laptop Screen (15.6\" HD/FHD LED)","unit_price":3000.0,"quandity":1.0,"total_price":3000.0,"parent":"JC-2026-00011","parentfield":"parts_used","parenttype":"Job Card","doctype":"Part Usage Entry"}]}}
    ```
- req3 : POST /api/resource/Spare Part
    res : 
    ```json
    {"data":{"name":"PART-2026-0009","owner":"Administrator","creation":"2026-05-14 15:46:19.177289","modified":"2026-05-14 15:46:19.177289","modified_by":"Administrator","docstatus":0,"idx":0,"part_name":"sample part","compatible_device_type":"Laptop","unit_cost":30.0,"selling_price":35.0,"stock_qty":0.0,"reorder_level":5.0,"is_active":1,"doctype":"Spare part"}}
    ```
- req4 : PUT /api/resource/Spare Part/PART-2026-0009
    res :
    ```json
    {"data":{"name":"PART-2026-0009","owner":"Administrator","creation":"2026-05-14 15:46:19.177289","modified":"2026-05-14 15:50:19.715587","modified_by":"Administrator","docstatus":0,"idx":0,"part_name":"sample part","compatible_device_type":"Smart Phone","unit_cost":30.0,"selling_price":35.0,"stock_qty":0.0,"reorder_level":5.0,"is_active":1,"doctype":"Spare part"}}
    ```
- req5 : DELETE /api/resource/Spare Part/PART-2026-0009
    res : 
    ```json
    {"data":"ok"}
    ```
## Why rate limiting is important for allow_guest=True

### Public guest APIs are accessible without login, so they are vulnerable to abuse.

#### Common attack vectors:

    Brute-force data enumeration
    attacker tries thousands of phone numbers
    leaks customer/job information
    Denial of Service (DoS)
    excessive requests overload workers/database
    slows down or crashes server
    Scraping / data harvesting
    automated bots collect business/customer data
    privacy and security risk

Additional risks:

    credential stuffing
    API abuse by bots
    database load amplification
    spam automation

# Server Scripts — Developer Reference

## What Is a Server Script?

A Frappe **Server Script** is Python code stored in the database and executed
in a restricted sandbox at runtime. No deployment, no `bench migrate` — changes
take effect immediately after saving.

---

## Blocked Functions & Modules

The sandbox strips dangerous builtins. These are **unavailable**:

| Blocked | Why |
|---|---|
| `import` (arbitrary) | Only a fixed whitelist of safe modules allowed |
| `open()`, `os`, `sys` | No filesystem or process access |
| `subprocess`, `shutil` | No shell execution |
| `socket`, `requests`, `urllib` | No outbound network calls |
| `eval()`, `exec()`, `compile()` | No dynamic code execution |
| `__import__()` | Import system locked |
| `globals()`, `locals()` | No runtime introspection |

**Safe modules available inside sandbox:**
`frappe`, `json`, `datetime`, `math`, `re`, `string`, `_dict`

---

## 3 Things You Cannot Do in a Server Script

**1. Call external APIs or send raw HTTP requests**
```python
#  Blocked in Server Script
import requests
requests.post("https://api.example.com/webhook", json=data)

# App code — api.py
import requests
requests.post(...)
```

**2. Import third-party libraries**
```python
# Blocked
import pandas as pd
import pyqrcode

#  App code only
import pyqrcode   # works fine in utils.py, api.py
```

**3. Read/write files or run shell commands**
```python
# ❌ Blocked
with open("/tmp/report.csv", "w") as f:
    f.write(data)

subprocess.run(["bench", "migrate"])

# ✅ App code only
import csv, subprocess
```

---

## When Server Scripts Are Acceptable

**Scenario 1 — Quick field validation on save**

Checking that `delivery_date` is not before `diagnosis_date` on a Job Card.
No imports needed, pure `frappe.db` and `frappe.throw`. Safe, fast to ship,
easy for a non-developer admin to tweak without a deployment.

```python
# Doc Event → Job Card → before_save
if doc.delivery_date and doc.diagnosis_date:
    if doc.delivery_date < doc.diagnosis_date:
        frappe.throw("Delivery date cannot be before diagnosis date.")
```

**Scenario 2 — Auto-assign a field on submit**

Stamping `submitted_by` and `submitted_at` when a Service Invoice is submitted.
Single-document scope, no external dependencies, no logic complex enough to
warrant version control.

```python
# Doc Event → Service Invoice → on_submit
doc.submitted_by = frappe.session.user
doc.submitted_at = frappe.utils.now()
doc.save()
```

---

## When You Must Use App Code Instead

**Scenario 1 — QR code generation in a print format**

`pyqrcode` is a third-party library. The sandbox blocks all non-whitelisted
imports. Must live in `utils/utils.py`, registered in `hooks.py` under `jinja.methods`.

```python
#  Server Script — import pyqrcode → ImportError
# quickfix/utils/utils.py
import pyqrcode
def get_qr_code(name): ...
```

**Scenario 2 — Monthly revenue background job**

`generate_monthly_revenue_report` uses `frappe.enqueue`, `frappe.publish_progress`,
`calendar.monthrange`, and complex multi-month DB logic. Server Scripts cannot
be called by `frappe.enqueue` as a dotted path, cannot use `@frappe.whitelist`,
and have no access to the `calendar` module. Must be app code.

---

## Governance & Maintainability Risks

**1. No version control**
Server Scripts live in the database. There is no `git diff`, no PR review,
no rollback beyond Frappe's own document versioning. A bad edit goes live
the moment you click Save — with no audit trail visible to your dev team.

**2. Hidden logic, invisible to developers**
A developer reading `api.py` and `hooks.py` has no way to know a Server Script
also fires on the same DocType event. Business logic split across app code and
the database creates invisible side effects that are extremely hard to debug.

**3. No test coverage**
Server Scripts cannot be covered by `pytest` unit tests in your app's
`test_*.py` files. Bugs only surface in production or manual QA.

**4. Breaks on migration**
If a Server Script references a field that gets renamed or removed, it fails
silently at runtime with no deploy-time warning. App code catches these as
import errors or test failures before they reach production.

**5. Multi-developer conflict**
Two developers editing the same Server Script simultaneously produce a
last-write-wins conflict with no merge strategy. App code uses Git — conflicts
are resolved before merge.

---

## Quick Decision Rule

```
Does it need an import beyond frappe/json/datetime/math/re?
    YES → App code

Does it run in a background worker or get called by frappe.enqueue?
    YES → App code

Is it complex enough to need a unit test?
    YES → App code

Is it a simple field validation or auto-fill on a single DocType?
    YES → Server Script is fine
```

---

## File Placement Reference

```
quickfix/
├── api.py                  ← @whitelist methods, background jobs
├── scheduled_jobs.py       ← scheduler targets (daily/hourly/cron)
├── utils/
│   └── utils.py            ← Jinja helpers (get_qr_code, get_shop_name)
└── quickfix/
    └── doctype/
        └── job_card/
            └── job_card.py ← DocType class methods (validate, on_submit)
```

Server Scripts replace `job_card.py` class methods only for simple cases.
Everything else belongs in the files above.

## Production debugging patter
- If a bug occurs only in production in Frappe Framework and cannot be reproduced in development, I would debug it using Error Log, Audit Log, and frappe.logger() without enabling developer_mode.

- First, I would inspect Setup → Error Log to identify the exact exception, traceback, affected method, timestamps, and related document references using fields like method, error, reference_doctype, reference_name, and trace_id. This helps locate where the failure occurred in production.

- Next, I would correlate the failure with entries in the custom Audit Log DocType to reconstruct the business flow before the error occurred. For example, I would check whether a Job Card was submitted, whether a webhook retry happened, which user triggered the action, and whether duplicate processing occurred.

**SQL Injection Prevention**
SQL injection happens when user input is embedded directly into a database query string, letting attackers manipulate the query logic. In Frappe, f-strings like `f"SELECT * WHERE phone='{phone}'"` are dangerous because malicious input like `' OR '1'='1` changes the query's meaning entirely. Parameterized queries pass user data separately from the SQL template using `%s` placeholders, so the database driver never interprets the input as code. `frappe.db.escape()` exists to manually sanitize strings but is fragile — developers must remember to call it every time, and edge cases exist. The Frappe ORM (`frappe.get_all()` with a `filters` dict) is the best approach because it is fully parameterized by default. The rule is simple: never concatenate user input into SQL; always let the driver handle data separately from code.

---

**allow_guest Risks**
`allow_guest=True` makes an endpoint publicly accessible with zero authentication, meaning anyone on the internet can call it. Without input validation on the phone number, three attacks become trivial: SQL injection (if the phone touches a raw query), enumeration (automated scripts loop through thousands of numbers to discover which ones have accounts), and denial of service (flooding the endpoint with requests exhausts database connections). Sanitizing the phone to digits-only with a 10-character maximum ensures the value cannot carry SQL payloads or abnormal data. Checking that at least one job exists before returning any response prevents enumeration — an attacker gets no useful signal from a failed lookup. A rate limiter keyed on IP address caps how many requests any single caller can make per minute, neutralizing the flood attack. Together these three defenses cover the full surface area the open endpoint exposes.

---

**ignore_permissions Analysis**
`ignore_permissions=True` tells Frappe to skip all role-based permission checks for a database operation, regardless of who the current user is. It is legitimate only in system-initiated contexts: background jobs, schedulers, webhook handlers, and after-submit hooks that run under a system user with no human session. In each of those cases the action is automated business logic, not a response to a user's direct request, so the bypass is justified. The danger arises when a developer adds it to a user-facing endpoint — and the worst case is combining it with `allow_guest=True`. That combination means any anonymous person on the internet can read, write, or delete any document in the system because both the authentication check and the permission check are disabled simultaneously. Frappe's entire security model collapses to nothing with those two lines together.

---

**Private vs Public Files**
Frappe stores uploaded files in two separate directories with fundamentally different access rules. Files in `/public/files/` are served directly by Nginx — anyone with the URL can download them instantly with no login. Files in `/private/files/` are never served by Nginx directly; Frappe's Python middleware intercepts the request, checks whether the user has an active session and the correct document permission, and only then streams the bytes. Trying to access a private file via a direct `/files/filename.pdf` URL returns a 404 because no Nginx route exists for that path. Accessing `/private/files/filename.pdf` requires a valid login and Read permission on the linked document. Private files are appropriate for anything sensitive — invoices, contracts, customer records, medical documents. Public files are appropriate for assets that are intentionally world-readable like product images or marketing brochures.

---

**Secrets Management**
Hardcoding an API key directly in Python source code means the secret is readable by every developer, contractor, or intern with file access, and it travels into version control where it becomes permanent. `frappe.conf.get("payment_api_key")` reads the value from `site_config.json` on the server filesystem, which is never served to clients and should never be committed to git. `common_site_config.json` is the wrong place for secrets because it applies to every site on the bench, so a single file's exposure compromises all sites at once — and it is frequently included in deployment scripts that are version-controlled. Committing `site_config.json` to git is particularly dangerous because git history is permanent: even after the file is deleted, every past commit and every clone of the repository still contains the secret. If a secret is ever committed, the only correct response is to treat it as already compromised and rotate it immediately — scrubbing history is helpful but cannot guarantee the secret was not already harvested.

## Frappe & ERPNext CI Workflow Notes

### What Linux service containers does the Frappe CI workflow need and why? What breaks if MariaDB is missing?

Frappe CI usually needs these service containers:

* **MariaDB** → Main database used by Frappe to store DocTypes, records, users, permissions, etc.
* **Redis Queue** → Used for background jobs and task queues.
* **Redis Cache** → Used for caching metadata, sessions, and realtime data.

If MariaDB is missing:

* `bench new-site` fails
* Sites cannot be created
* DocTypes cannot be installed
* Tests cannot run because Frappe depends fully on the database.

---

### Why does the ERPNext CI workflow use `--skip-assets` when installing apps?

`--skip-assets` skips frontend asset building during CI setup.

This makes CI much faster because:

* JS/CSS bundling is slow
* Most backend tests do not need compiled frontend assets
* CI mainly checks Python logic, database behavior, and tests

ERPNext uses it to reduce pipeline execution time.

---

### What is the purpose of `bench start` in CI versus `bench serve`? Does CI need either?

* `bench start` runs the full development stack:

  * web server
  * Redis workers
  * scheduler
  * socketio
  * file watcher

* `bench serve` runs only the web server.

CI usually needs neither because tests run directly using:

```bash
bench --site test_site run-tests
```

The CI pipeline only needs the database and Python environment, not an interactive development server.

---

### What happens to the test site after the CI run completes? Is cleanup needed?

The GitHub Actions runner is temporary.

After the workflow finishes:

* the Ubuntu VM is destroyed
* the test site is deleted automatically
* databases and files are removed with the runner

Manual cleanup is usually not needed in CI.

## Test Data Strategy Notes

### Why it is dangerous to put Job Card or Technician records in fixtures?

Job Card and Technician are transactional records. Tests may modify, submit, cancel, or delete them. Shared fixture data can make tests depend on each other and cause inconsistent CI failures.

### What happens if a mandatory field is added to Spare Part but fixture is not updated?

The CI pipeline fails during fixture loading or test setup because the old fixture JSON does not contain the new mandatory field value.

### Why should test fixtures and production/demo fixtures stay separate?

Test fixtures are only for automated testing and may contain fake or resettable data. Mixing them with production/demo fixtures can pollute real environments and make deployments unsafe.

## Why is `ignore_if_duplicate=True` important?

`ignore_if_duplicate=True` prevents Frappe from throwing a duplicate entry error if the same record already exists in the database.  

This is essential for test setup scripts because CI pipelines, local tests, or repeated setup commands may run multiple times. Without it, fixture loading would fail on the second run when records already exist.

---

## Why are Device Type records present in both `fixtures/` and `fixtures/test/`?

This duplication is intentional.  

- `fixtures/` contains production or deployment fixtures needed when the app is installed normally.
- `fixtures/test/` contains test-specific data loaded explicitly during CI/testing.

Keeping them separate ensures test environments are predictable and isolated from production/demo data. It also allows test fixtures to evolve independently without affecting deployment fixtures.
