> Using a "dangerous" env var like `LD_PRELOAD` could allow to escape the plugins default entrypoint to execute malicious code using privileged permissions of an escalated plugin.
> 
> [https://stackoverflow.com/questions/426230/what-is-the-ld-preload-trick](https://stackoverflow.com/questions/426230/what-is-the-ld-preload-trick)

_Originally posted by [@anbraten](https://github.com/anbraten) in [https://github.com/woodpecker-ci/woodpecker-security/issues/10](https://github.com/woodpecker-ci/woodpecker-security/issues/10)_

[GHSA-3wf2-2pq4-4rvc](https://github.com/advisories/GHSA-3wf2-2pq4-4rvc "GHSA-3wf2-2pq4-4rvc")