---
outline: deep
---

# Kubernetes

`ssebench run --backend kubernetes` runs each run as a Job on a Kubernetes cluster
instead of a container on the local Docker daemon. The runner, the grading and the
results are the same; only [where the containers execute](/concepts/runner-backends)
changes. This page describes what the backend creates, what it needs from the
cluster, and which of the [integrity protections](/concepts/integrity) it keeps.

```
                            cluster, namespace "ssebench"
 ssebench run  ---- API ---->  Job ssebench-<run id>
   (a laptop, or                 pod ── task       the prebuilt image, as it is
    a pod)                            └─ collector waits, so the results can be read out
                               Secret         the run's environment and files
                               NetworkPolicy  DNS and the proxy only; nothing gets in
                             Service litellm  the LiteLLM proxy, in the cluster
```

The backend runs [prebuilt images](/concepts/runner-backends#prebuilt-images) and
builds nothing, so it needs `--prebuilt` (or `SSEBENCH_PREBUILT=1`). It supports the
sandbox mode; [sidecar mode](/concepts/sandbox-and-sidecar#sidecar-mode) is refused
with an error, because its two containers would need the project's files copied
between them before they start.

## Requirements

| What | Why |
|---|---|
| A cluster and a kubeconfig, or `ssebench` running in a pod | Tested on Kubernetes 1.35 with Calico 3.31; it uses only Job, NetworkPolicy and Secret features that have been stable for years. Inside a pod the backend uses the pod's service account |
| `pip install 'ssebench[kubernetes]'` | The Python client is an optional dependency, imported when the backend is used |
| **A network plugin that enforces NetworkPolicy** | Calico, Cilium and the cloud providers' policy engines do. A plugin that does not, such as the default one of a kind cluster or Flannel alone, accepts the policy and ignores it, and the run then has the internet. See [Egress](#egress) |
| The prebuilt images, where the nodes can pull them | `<registry>/agent-<agent>/<task>:<version>` for every task and agent. Set `SSEBENCH_REGISTRY` to the registry, and `SSEBENCH_K8S_IMAGE_PULL_SECRETS` if it needs a login. In kind, `kind load docker-image` puts them on the nodes |
| A LiteLLM proxy Service in the cluster | Runs reach the model through it. The Helm chart installs one; [`deploy/k8s/litellm-test.yaml`](https://github.com/42-b3yond-6ug/ssebench/blob/main/deploy/k8s/litellm-test.yaml) is a throwaway one for trying the backend |
| Node disk for `emptyDir` volumes | A run writes its results and the agent's archive to two `emptyDir` volumes and builds in its container's file system. No storage class or PersistentVolume is needed |
| An identity with the [RBAC](#rbac) role | Whoever runs `ssebench`: you, or the controller's service account |

The proxy's admin key is the `LITELLM_MASTER_KEY` setting, as with the local stack.
The provider keys belong to the proxy in the cluster, not to the machine that runs
`ssebench`.

## Try it on kind

```sh
# 1. A cluster with a network plugin that enforces policy
kind create cluster --name ssebench --config deploy/k8s/kind.yaml
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.31.0/manifests/calico.yaml
kubectl -n kube-system rollout status daemonset/calico-node

# 2. The images of a task and agent (see "Prebuilt images"), loaded into the nodes
kind load docker-image --name ssebench "$SSEBENCH_REGISTRY/agent-reference/gjson-196-bf4efcb:1.0.0-dev"

# 3. The namespace, the role, and a proxy to talk to
kubectl create namespace ssebench
kubectl apply -n ssebench -f deploy/k8s/rbac.yaml
kubectl apply -n ssebench -f deploy/k8s/litellm-test.yaml   # only for runs that use a model

# 4. Run
export SSEBENCH_K8S_NAMESPACE=ssebench SSEBENCH_REGISTRY=<registry>
uv run ssebench run --backend kubernetes --prebuilt --task gjson-196-bf4efcb --agent reference
```

The `reference` agent makes no model calls, so it needs no proxy. A run with a
model needs the proxy's admin key and a way to reach it from your machine:

```sh
kubectl -n ssebench port-forward svc/litellm 4000:4000 &
LITELLM_MASTER_KEY=... uv run ssebench run --backend kubernetes --prebuilt \
  --task gjson-196-bf4efcb --agent dummy --model claude-sonnet-4-6
```

Output of the task container appears in your terminal as it is written, and
`results/<task>/<model>/<agent>/<run id>/` holds the same files as after a Docker run.

## What a run creates

For a run with ID `<id>`, in one namespace, the backend creates three objects and
removes them when the run ends (`--keep-container` keeps them):

| Object | Name | Content |
|---|---|---|
| NetworkPolicy | `ssebench-<id>` | What the run's pod may reach; see [Egress](#egress) |
| Secret | `ssebench-<id>` | The run's environment, which holds its model key, and the reference patch for a `reference` run. The Job does not repeat them in its own spec |
| Job | `ssebench-<id>` | One pod, no retries |

The Secret and the NetworkPolicy are owned by the Job, so the cluster removes them
with it. The name is the run ID made into a DNS label; the exact ID is in the labels.

### The Job

- **One pod, one attempt** (`backoffLimit: 0`, `restartPolicy: Never`): a failed
  run is not repeated.
- **`activeDeadlineSeconds`** is the run's `--timeout` plus `SSEBENCH_K8S_DEADLINE_SLACK`
  (30 minutes), for pulling images, starting and grading. The container enforces the
  timeout itself; the deadline is the cluster's backstop. When it passes the cluster
  deletes the pod and the run's results with it.
- **`ttlSecondsAfterFinished`** is `SSEBENCH_K8S_TTL_SECONDS` (an hour): the cluster
  removes a finished Job and its pod, even if `ssebench` died before it could.
  A kept run has none.
- **Resources.** The task container requests 1 CPU, 2Gi of memory and 2Gi of
  ephemeral storage, and is limited to 4 CPUs, 8Gi and 20Gi. `SSEBENCH_K8S_RESOURCES`
  replaces these with any `requests` and `limits` a container accepts.
- **`runtimeClassName`** is `SSEBENCH_K8S_RUNTIME_CLASS`, to run the pod under
  gVisor or Kata Containers.

Every object carries the run's labels: `ssebench.run-id`, `ssebench.task-id`,
`ssebench.agent`, `ssebench.model`, `ssebench.webui`, and
`app.kubernetes.io/managed-by=ssebench`. The run directory on the runner's host
(`ssebench.results`) is not a valid label value, so it is an annotation.
[`list_runs` and `inspect_run`](/concepts/runner-backends#the-interface) accept it as
a label all the same.

```sh
kubectl get jobs -n ssebench -l ssebench.agent=reference
kubectl logs -n ssebench -l ssebench.run-id=<id> -c task
```

### The pod

The pod has two containers of the same image:

- **`task`** runs the image as it was built, with its entrypoint and the run's
  environment. The run waits for it and its exit status is the run's.
- **`collector`** only waits. The results are files in the pod's volumes, and once
  `task` has exited something must still be running in the pod for them to be read
  out. It exits when `ssebench` has read them, or when the deadline passes.

## Results

The container writes the grade, the graded patch and the logs to
`/var/lib/ssebench/results`, and the agent writes its own files to
`/tmp/sse-archive`. In the pod these are two `emptyDir` volumes, limited to 2Gi
each. After the task container exits, the backend reads both out of the collector
with the Kubernetes API, as `kubectl cp` does (`tar` over `pods/exec`), and unpacks
them into the run directory on the runner's host. Then it deletes the Job.

The two volumes are unpacked separately: the results into the run directory, and the
archive into its `archive/` directory. So the `result.json` that the runner grades is
always the file that root wrote to the results volume, however the agent fills its
archive. Because the agent writes the archive, its tar stream is not trusted: only
regular files and directories are unpacked, never through a link, never outside the run
directory, and no more than 2 GiB or 200 000 files. Anything else is skipped, and a
stream that breaks these rules fails the collection.

A run whose pod is gone before the results are read, for example after the deadline
or a node failure, has no results. The runner records it as it does any run without a
grade.

## Security properties

The task container is the one a Docker run uses, so the
[protections inside it](/concepts/integrity#the-protections) are the same: the entrypoint
runs as root, starts the daemon, and runs the agent as `model`, task scripts as
`sse-runner`, with the task files, the results and the admin socket root-only. What the
Kubernetes backend adds or changes is around the container.

| Property | How |
|---|---|
| **Not privileged, not a host process** | `privileged: false`, no `hostPath` volumes, and no `hostNetwork`, `hostPID`, `hostIPC` or shared process namespace. The pod has no service account token and no service environment variables |
| **Root, but few capabilities** | The entrypoint needs root to become other users, so the container runs as uid 0 with all capabilities dropped except `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID` and `SETUID`, which it needs to prepare and enter the users' directories and to become them, and `KILL`, with which root clears the leftover processes of the other users after a check. Without any of the first five a run is not graded. The agent's own processes have no capabilities at all |
| **No privilege gain** | `allowPrivilegeEscalation: false` (`no_new_privs`), so a setuid program the agent finds gives it nothing, and the container's default seccomp profile (`RuntimeDefault`) |
| **Results readable only by root** | The results are in a volume whose parent directory in the container is `0700` root, as in Docker. The collector reads them with root and `DAC_READ_SEARCH`; it mounts them read-only, and it is not reachable from the agent's container |
| **Runs cannot see each other** | Each pod has its own volumes and its own NetworkPolicy, which admits no ingress. One run cannot reach another's daemon on port 4263, unlike two containers on the same Docker network |
| **The model key is not in the Job** | It is in a Secret, and the Job refers to the Secret |
| **Optional sandboxed runtime** | `SSEBENCH_K8S_RUNTIME_CLASS` puts each pod in a gVisor or Kata sandbox, which a Docker run cannot do without extra setup |

### Egress

The NetworkPolicy of a run selects its pod by the `ssebench.run-id` label and lists
both `Ingress` and `Egress`, with no ingress rule at all.

| `--egress` | The pod can reach |
|---|---|
| `restricted` (default) | The cluster's DNS (`kube-dns` in `kube-system`, port 53), and the pods of the LiteLLM proxy on its port. Nothing else: not the internet, not other pods or services, not the Kubernetes API, not the nodes or the cloud metadata service |
| `open` | The same, and every address outside the private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`, `169.254.0.0/16`). So it has the internet but still not the cluster |

The proxy pods are those of `SSEBENCH_K8S_PROXY_NAMESPACE` (default: the runs'
namespace) with the labels `SSEBENCH_K8S_PROXY_SELECTOR` (default
`app.kubernetes.io/name=litellm`), and the port is the one in the run's proxy URL
(`SSEBENCH_K8S_PROXY_URL`, default `http://litellm.<namespace>.svc:4000`). A Service
that maps another port onto the pods' port needs the URL to use the pods' port.

::: warning The cluster must enforce NetworkPolicy
Kubernetes accepts a NetworkPolicy whether or not anything enforces it. On a cluster
whose network plugin does not, `restricted` runs have the internet, and with it the
upstream fix. Check each cluster once with a kept run, which stays up after grading:

```sh
ssebench run --backend kubernetes --prebuilt --agent reference --task <task> \
  --run-id netcheck --keep-container &
# when the log says the container waits to be stopped:
POD=$(kubectl get pod -n <ns> -l ssebench.run-id=netcheck -o name)
kubectl exec -n <ns> $POD -c task -- curl -sS -m 5 https://example.com
```

`curl` must time out. Then stop the run as described under
[Stopping and cleaning up](#stopping-and-cleaning-up).
:::

DNS is open in both policies, so a pod resolves outside names through the cluster's
DNS, which forwards them. It cannot connect to what it resolves, but the
DNS traffic itself is a channel: an agent could look up a name that carries data to a
server it controls. If that matters, give the cluster's DNS a configuration that
answers cluster names only.

The policy applies from the moment the pod exists, since it is created before the Job,
but a network plugin programs a new pod's rules a moment after the pod starts. The task
container needs several seconds to start its services, long before an agent runs.

### What is not different

- **The pod shares the node's kernel** unless a runtime class sandboxes it, as a Docker
  container shares the host's. Run only agents you are prepared to run that way.
- **`--egress open`** gives the agent the upstream repository and its fix, as in
  Docker.
- **The model is outside the pod.** The proxy forwards to the provider, whose hosted
  tools run outside the network policy.
- **Node-local DNS caches** on link-local addresses (`169.254.20.10`) are outside the
  DNS rule of the policy, and blocked. Allow them in the cluster if you use one.
- **Dual-stack clusters.** The `open` policy allows IPv4 addresses only.

## RBAC

[`deploy/k8s/rbac.yaml`](https://github.com/42-b3yond-6ug/ssebench/blob/main/deploy/k8s/rbac.yaml)
defines a service account, a `Role` and a `RoleBinding` for one namespace, which
is all `ssebench` needs. It cannot read Secrets, or anything outside the namespace.

| Resource | Verbs | For |
|---|---|---|
| `jobs` | create, get, list, delete | The run |
| `pods` | create, get, list, delete | Following the run, and the short pod that copies the reference patch out of an image |
| `pods/log` | get | The run's output |
| `pods/exec` | create, get | Reading the results out, and stopping the task container. `get` is for clusters before 1.30 |
| `secrets` | create, patch, delete | The run's environment, and its owner reference |
| `networkpolicies` | create, patch, delete | The run's network policy, and its owner reference |

`pods/exec` is the powerful one: it runs commands in any pod of the namespace. Give
the runs a namespace of their own, and do not bind the role in a namespace that holds
anything else. A `ssebench` process inside the cluster uses the same role through the
pod's service account.

## Stopping and cleaning up

- `Ctrl-C` or SIGTERM on `ssebench run` stops the task container as `docker stop`
  does: it sends SIGTERM to the container's entrypoint (`kill -TERM 1`), which
  cleans up, and the backend reads the results before removing the Job. A container
  that does not stop within 20 seconds is deleted with the Job, and its results with it.
  A second signal ends `ssebench` at once and leaves the Job to its deadline and time
  to live.
- `--keep-container` keeps the Job, the pod, the Secret and the policy, and the task
  container keeps running after grading. End it, and so the run, with
  `kubectl exec -n <ns> <pod> -c task -- sh -c 'kill -TERM 1'`, and remove the objects with
  `kubectl delete job,secret,networkpolicy -n <ns> -l ssebench.run-id=<id>`.
- A run that never starts fails: `ssebench` reports the reason from the pod (an image
  that cannot be pulled, a missing Secret, no node with room) after
  90 seconds of pull errors or 10 minutes without a container.

## Limits

- Sandbox mode only, and prebuilt images only.
- The images are pulled for the node's architecture from a multi-arch image; the
  backend does not choose a node by architecture.
- `emptyDir` volumes are node-local, so a run that outlives its node loses its results.
- The web UI lists Docker containers; it does not see Kubernetes runs yet.

## Next steps

- [Runner backends](/concepts/runner-backends): the interface this backend implements
- [Integrity and egress](/deployment/integrity-and-egress)
- [Integrity model](/concepts/integrity)
- [LiteLLM proxy](/concepts/litellm-proxy)
