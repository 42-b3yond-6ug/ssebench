# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability
reporting:
[open a draft security advisory](https://github.com/42-b3yond-6ug/ssebench/security/advisories/new)
(the "Report a vulnerability" button on the repository's Security tab).
If you cannot use GitHub, email [whexy@outlook.com](mailto:whexy@outlook.com)
instead.

Do not open a public issue, pull request or discussion for a vulnerability.
This includes benchmark-integrity bypasses: once a bypass is public, anyone
can use it to inflate results before it is fixed.

A useful report says which component and version or commit is affected, how to
reproduce the problem (for integrity issues: the task, agent, mode and
difficulty level), and what an attacker or agent gains. The maintainers will
acknowledge the report in the advisory, work with you on a fix, and credit you
in the published advisory unless you ask not to be named.

## Supported versions

Fixes go into the `main` branch and the next release. Older releases are not
patched.

## Scope

**Benchmark integrity.** SSEBench treats a way for the agent under test to get
information or signals it should not have as a vulnerability. Examples:

- the agent reads the reference patch, the hidden tests or the upstream fix
  commit from inside its container, for example through the filesystem, the
  daemon, the MCP server, environment variables or leftover git objects;
- the agent obtains a check that its difficulty level withholds, such as PoC
  or intent-test results at the default `NO_FUTURE_TEST` level;
- the agent tampers with grading: it changes the evaluator, the tests, the
  PoCs or `result.json`, or makes a failing patch grade as passing.

**Isolation and host safety.** Examples:

- escaping a task container, or reaching the host or other containers beyond
  what the run needs;
- command injection or unauthenticated control of the host through the web UI,
  its terminal proxy or the catalog service;
- leaking provider API keys or proxy credentials outside the components that
  need them.

**Out of scope**

- The vulnerabilities in `datasets/pilot/`. They are known, publicly disclosed
  and fixed upstream; reproducing them is the point of each task. Report new
  issues in those projects to their maintainers.
- Vulnerabilities in third-party agents, model providers, LiteLLM or base
  image packages, unless SSEBench's configuration makes them exploitable.
  Report those upstream.
- Running untrusted agents or tasks outside the provided containers, or
  exposing the web UI or proxy to an untrusted network against the
  documentation.
