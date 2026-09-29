# ssebench-sdk

The Python SDK of [SSEBench](https://github.com/42-b3yond-6ug/ssebench), a
benchmark that measures how well AI coding agents fix real security
vulnerabilities. It is imported as `sse`.

Code that runs inside an SSEBench task container uses the SDK: an agent reads
the task and checks its patch with the build, test and proof-of-concept
actions, and the evaluator grades the result. The SDK is a client of
`ssebench-daemon`, which serves those actions over the Unix socket named by the
`SSE_DAEMON_SOCKET` environment variable. It does nothing useful outside a task
container.

## Install

```sh
pip install ssebench-sdk==<version>
```

Use the version of the SSEBench release you run against; see
[Versions](#versions). The SDK needs Python 3.12 or newer. An agent that runs in
a task container installs it into its own environment; the `reference` agent in
the SSEBench repository, `agents/reference`, is the smallest example.

## Use

```python
from sse import project

print(project.metadata.id, project.source)
result = project.build()
if result.is_success():
    print(project.function_test().stdout)
```

`import sse` does not contact the daemon. `sse.project` and `sse.prompt` ask it
for the task when they are imported, so import them only inside a task
container.

## Versions

SSEBench components share one version and are released together, so
`ssebench-sdk` `X` is made for `ssebench-daemon` `X`. Install the SDK version
that matches the SSEBench release whose task container your code runs in, for
example by pinning `ssebench-sdk==X`. When the SDK connects, it reads the
daemon's version from `GET /version` and logs a warning if the two differ. The
warning does not stop your code, but the two may disagree about the API, so
treat it as a sign to fix the pin.

`sse.__version__` holds the SDK's version. SSEBench writes the same version as
`1.2.0-rc.1` in `VERSION` and in the daemon, and as `1.2.0rc1` in Python
packages; they name the same release.

## Documentation

- [Python SDK reference](https://github.com/42-b3yond-6ug/ssebench/blob/main/docs/reference/python-sdk.md)
- [Daemon API](https://github.com/42-b3yond-6ug/ssebench/blob/main/docs/reference/daemon-api.md)
- [SSEBench repository](https://github.com/42-b3yond-6ug/ssebench)

The SDK is licensed under the Apache License 2.0.
