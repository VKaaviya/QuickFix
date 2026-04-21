### Quickfix

Management app for electronics repair shop

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

### Routing 
- For every http reques the application function is called by the frappe app.py
- application function set the local config,db connection by init_request and do the authendication by validate_auth function and after that the url mapped to handle function if it started by "api/".
- handle function handles the request route  match in API_RULE mapping.
- "api/method/.." this type of endpoints are call the whitelisted function 
- whitelisted endpoints are used to produce the web to users/guests and provide customized endpoints.
- the function is processed by seperating the end points last name by the '.'. (ex: quickfix.api.method structure : quickfix/api/method.py)
- after that function is called by the execute_cmd(cmd)
- for "api/resources/..." endpoints the functions like get_doc update or etc are call by the url structure.
- this also v1 so the v1.py file handles this request
- There is some url rules used to map and call the correct function regarding to the end points
- the url rules divide into v1 and v2 