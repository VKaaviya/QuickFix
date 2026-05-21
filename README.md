
[![CI](https://github.com/VKaaviya/QuickFix/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/VKaaviya/QuickFix/actions/workflows/ci.yml)

### Quickfix

Management app for electronics repair shop

*For the detailed internal answers and task writeups, see `README_internals.md`.*

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch master
bench install-app quickfix
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/quickfix
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit

## Configuration Files
site_config.json
- Used to define configuration settings for a specific site. Each site can have its own independent configuration.
common_site_config.json
Used for bench-level (global) configurations that apply to all sites within the bench.
Security Note
Storing sensitive information (like passwords, API keys, secrets) in common_site_config.json is not recommended, as it increases the risk of exposure across multiple sites.
Bench Start Process

# When you run bench start, the following services are launched:

* Web server
* Background workers
* Redis Cache
* Redis Queue
* Redis SocketIO

Job Queue Handling
- Jobs are added (enqueued) into the Redis Queue.
- The queue’s role is to store jobs, not execute them.
- Workers are responsible for picking up and executing these jobs.

Fault Tolerance
- If a worker crashes, the jobs are not lost because they remain in the queue.
- Once the worker restarts, it resumes processing the pending jobs from the queue.

## ORM internal and Query builder
- the tab prefix in frappe is used to idendify the tables which are maintained by frappe. it avoids the misunderstanding with already created tables like user.
    In [3]: import frappe;frappe.db.sql("SHOw TABLES LIKE '%Job%'")
    Out[3]: (('tabJob card',), ('tabScheduled Job Log',), ('tabScheduled Job Type',))
    In [4]: import frappe;frappe.db.sql("DESCRIBE `tabJob card`",as_dict=True)
    Out[4]: 
    [{'Field': 'name',
    'Type': 'varchar(140)',
    'Null': 'NO',
    'Key': 'PRI',
    'Default': None,
    'Extra': ''},
    {'Field': 'creation',
    'Type': 'datetime(6)',
    'Null': 'YES',
    'Key': 'MUL',
    'Default': None,
    'Extra': ''},
        .....]

## Docstatus
- `docstatus` indicates a document workflow state: 0 = Draft, 1 = Submitted, 2 = Cancelled.
- Draft documents (`docstatus=0`) can be edited, saved, and deleted.
- Submitted documents (`docstatus=1`) are considered final and should not be modified directly.
- Cancelled documents (`docstatus=2`) are inactive and keep a record of the original submission.
- Use `submit()` to move a draft to submitted, and use `cancel()` to cancel a submitted document.
- Calling `save()` on a submitted document is not allowed in normal workflow unless the document is first amended or reverted by application logic.

## Document hooks internals
- `on_trash` is called when a document is deleted. For `Job Card`, deletion should only be allowed when status is `Draft` or `Cancelled`.
- Preventing deletion for status values like `Pending Diagnosis`, `In Repair`, or `Delivered` preserves audit history and avoids removing active business records.
- `on_update` is called every time a document is saved.
- Do not call `self.save()` inside `on_update`.
  - `save()` itself triggers `on_update`, so calling it again causes recursion and repeated processing.
  - This can lead to infinite loops, duplicated side effects, and stack overflow.
- The correct pattern is to move update logic into helper methods and let the outer save operation complete once.
  - e.g. `on_update()` should adjust fields or recalculate values, not re-save the document.

## Document modification conflict
- The error "Document has been modified after you have opened it" occurs when the document in the database has changed after you loaded it in the form.
- Frappe detects this by comparing the document’s saved `modified` timestamp with the current value in the database before applying the update.
- If the timestamps differ, Frappe blocks the save and shows the conflict message so you do not accidentally overwrite someone else’s changes.
- This prevents concurrent overwrites by forcing a refresh or reloading the latest document state before making new edits.

### Routing 
- For every HTTP request, the application() function in frappe/app.py is called first.
- The application() function initializes the request context by calling init_request(), which sets up local configuration, the database connection, and request data. It then performs authentication using validate_auth().
- If the request path starts with /api/, the request is passed to the API handle() function.
- The handle() function matches the incoming request against the routes defined in API_URL_MAP.
- Endpoints such as /api/method/... are used to call whitelisted Python functions.
- Whitelisted methods are commonly used to expose custom server-side logic through HTTP endpoints, including guest-accessible APIs when explicitly allowed.
- For a dotted path such as quickfix.app_call.get_data, Frappe resolves the module path, loads the function, and then executes it through execute_cmd(cmd).
- Endpoints such as /api/resource/... are used for resource-based operations like listing, reading, creating, updating, and deleting documents.
- In the older API structure, /api/resource/... requests are handled by v1.py.
- URL rules are used to map each endpoint pattern to the correct handler function.
- Frappe separates API routing into versioned rule sets, mainly v1 and v2.

## CSRF Token and Session Data

### X-Frappe-CSRF-Token
- In browser developer tools, the `X-Frappe-CSRF-Token` header in a POST request comes from `frappe.csrf_token` on the client side.
- Frappe includes this token in Desk and website pages and sends it with AJAX requests.
- On the server side, the token value is stored in `frappe.session.data.csrf_token`.
- If the token does not exist yet, Frappe generates one and saves it in the current session.
- During unsafe requests such as `POST`, `PUT`, `DELETE`, and `PATCH`, Frappe compares the incoming `X-Frappe-CSRF-Token` header with the token stored in the session.
- If the token is omitted or does not match, Frappe raises a CSRF validation error and the request is rejected as `Invalid Request`.

### frappe.session.data in bench console
- When you run `import frappe; frappe.session.data` in bench console, it often returns an empty dictionary such as `{}`.
- This is because `frappe.session.data` only contains extra session values stored for the current session.
- In a real request, Frappe first initializes a default session and then loads the active session through the authentication flow.
- Values such as `csrf_token` may be present in `frappe.session.data` during an actual browser request.
- In bench console, if no real HTTP session has been loaded or resumed, the session data can remain empty.


## Permission query & has_permission
- `get_permission_query_conditions` is used to add dynamic filters to a Doctype’s queries for views such as list and report. It is typically used to restrict records based on the current user’s role.
- `has_permission` is called for an individual record and checks whether the user has access to that specific document.
- When retrieving records from the database, `get_all` and `get_list` behave differently with respect to permissions. `get_all` bypasses Frappe role permissions and can expose all records and fields, which is a security risk.
- `get_list` enforces role permissions and applies filters correctly for each record, so it is safer to use when permission checks are required.

