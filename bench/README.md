# ssebench

The command-line tool of [SSEBench](https://github.com/42-b3yond-6ug/ssebench),
a benchmark that measures how well AI coding agents fix real security
vulnerabilities.

Every task is a publicly disclosed bug in an open-source C, Go or Rust project,
paired with its upstream fix. `ssebench` builds a Docker image for a task, runs
one agent with one model on it, and grades the patch the agent leaves behind:
does the project still build, does the proof of concept stop reproducing, and
do the project's tests pass. The `pilot` dataset has 55 tasks.

## Install and run

`ssebench` needs Docker with the buildx and Compose plugins, and Python 3.12 or
newer. It runs without a clone of the repository: the wheel carries the agent
definitions, the model list, the Compose file and the pilot manifest, and the
task images are pulled from the registry.

```sh
mkdir ssebench-work && cd ssebench-work
uvx ssebench init          # writes .env with generated secrets, models/ and results/
uvx ssebench doctor        # checks Docker, disk space and .env
uvx ssebench tasks list    # the 55 tasks of the pilot dataset

# The reference agent applies the task's known fix, so it needs no API key.
uvx ssebench run --task gjson-196-bf4efcb --agent reference

# A real agent needs the key of its model provider in .env.
uvx ssebench run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

Install it with `pip install ssebench` or `uv tool install ssebench` instead of
`uvx` to keep the command. Run it from the directory that `ssebench init` set
up: that directory holds `.env` and `models/`, and `results/` is written there.

The first run of a task pulls its case image and builds the tool and agent
layers on top of it, which takes a few minutes. The results are in
`results/<task>/<model>/<agent>/`.

## Versions

SSEBench components are released together under one version. `ssebench` pulls
the `runtime` image with the same version, and the SDK inside the task
container, `ssebench-sdk`, has the same version too.

## More

- [Documentation](https://github.com/42-b3yond-6ug/ssebench/tree/main/docs)
- [Source and issues](https://github.com/42-b3yond-6ug/ssebench)

Licensed under the Apache License 2.0.
