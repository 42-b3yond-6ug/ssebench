---
outline: deep
---

# Kubernetes

`ssebench run --backend kubernetes` runs each run as a Job on a Kubernetes cluster
instead of a container on the local Docker daemon. The runner, the grading and the
results are the same; only [where the containers execute](/concepts/runner-backends)
changes. This page describes what the backend creates, what it needs from the
cluster, and which of the [integrity protections](/concepts/integrity) it keeps, and
how to [install the whole stack with Helm](#install-with-helm).

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
| A LiteLLM proxy Service in the cluster | Runs reach the model through it. The [Helm chart](#install-with-helm) installs one; [`deploy/k8s/litellm-test.yaml`](https://github.com/42-b3yond-6ug/ssebench/blob/main/deploy/k8s/litellm-test.yaml) is a throwaway one for trying the backend |
| Node disk for `emptyDir` volumes | A run writes its results and the agent's archive to two `emptyDir` volumes and builds in its container's file system. No storage class or PersistentVolume is needed |
| An identity with the [RBAC](#rbac) role | Whoever runs `ssebench`: you, or the web UI's service account, which the chart binds to it |

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

## Install with Helm

The chart in [`deploy/helm/ssebench`](https://github.com/42-b3yond-6ug/ssebench/tree/main/deploy/helm/ssebench)
installs the parts of a cluster deployment and connects them:

```
  namespace "ssebench" (the release)            namespace "ssebench-runs" (runs.namespace)
  +-----------------------------------+         +-------------------------------------+
  |  web UI ----> catalog             |         |  Role, bound to the web UI's        |
  |    |                              |  API    |  service account                    |
  |    +------------------------------+-------> |  Job, Secret and NetworkPolicy      |
  |                                   |         |  of each run                        |
  |  LiteLLM proxy ---> Postgres      | <-------+-- the run's pod: its policy allows |
  |   (only the web UI and the runs   |         |  DNS and the proxy                  |
  |    may connect, by NetworkPolicy) |         +-------------------------------------+
  +-----------------------------------+
```

| Part | What it is |
|---|---|
| **LiteLLM proxy** and **Postgres** | The proxy that every run's model calls go through, with the models of the repository's `models/` directory (or your own file), and the database that holds the runs' keys. The provider keys come from Secrets that you made. A NetworkPolicy lets only the web UI and the run pods reach the proxy, and only the proxy reach the database |
| **Catalog** | Serves the task manifest that was bundled into its image, for the web UI's launcher |
| **Web UI** | The [web UI](/webui/) with `SSEBENCH_BACKEND=kubernetes`. It shows the runs of the runs' namespace, and, when you turn hosted mode off, launches them |
| **RBAC** | A service account for the web UI, and the [Role](#rbac) of `deploy/k8s/rbac.yaml` bound to it in the runs' namespace |

The runs' Jobs are not part of the release: the web UI or `ssebench run` creates them
when a run starts, and removes them when it ends.

### Install

You need Helm 3.8 or later, which installs charts from an OCI registry, and a cluster
that meets the [requirements](#requirements), above all a network plugin that enforces
NetworkPolicy. Make the runs' namespace and a Secret with the provider keys that your
models use, then install:

```sh
kubectl create namespace ssebench-runs
kubectl create namespace ssebench
kubectl -n ssebench create secret generic provider-keys \
  --from-literal=ANTHROPIC_API_KEY=... --from-literal=OPENAI_API_KEY=...

helm install ssebench oci://ghcr.io/42-b3yond-6ug/ssebench/charts/ssebench \
  --version <version> --namespace ssebench \
  --set litellm.providerKeySecrets={provider-keys} \
  --set runs.namespace=ssebench-runs
```

`<version>` is a release of SSEBench: the chart and the images have the same version, and
the images default to `ghcr.io/42-b3yond-6ug/ssebench/<name>:<version>`. From a checkout,
install `deploy/helm/ssebench` instead of the `oci://` address. The models of the
proxy are those of `models/anthropic-claude.yaml`, `openai-gpt.yaml` and
`google-gemini.yaml`; a model whose key is missing is listed but fails when a run
calls it.

The chart prints the commands you need after the install (`helm status` shows them
again). Its objects are named after the release, with `-ssebench` added unless the
release's name has it; the examples use a release named `ssebench`. The token and the
proxy's master key are in the Secret `ssebench-auth`:

```sh
# The web UI, at http://localhost:3001 (it asks for the token)
kubectl -n ssebench port-forward svc/ssebench-webui 3001:3001
kubectl -n ssebench get secret ssebench-auth -o jsonpath='{.data.SSEBENCH_WEBUI_TOKEN}' | base64 -d
```

To run a task from your machine instead, point `ssebench` at the release:

```sh
kubectl -n ssebench port-forward svc/ssebench-litellm 4000:4000 &
export SSEBENCH_BACKEND=kubernetes SSEBENCH_PREBUILT=1
export SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench SSEBENCH_K8S_NAMESPACE=ssebench-runs
export SSEBENCH_K8S_PROXY_NAMESPACE=ssebench SSEBENCH_K8S_PROXY_URL=http://ssebench-litellm.ssebench.svc:4000
export SSEBENCH_K8S_PROXY_SELECTOR=app.kubernetes.io/name=litellm,app.kubernetes.io/instance=ssebench
export LITELLM_MASTER_KEY=$(kubectl -n ssebench get secret ssebench-auth -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)
ssebench run --agent reference --task gjson-196-bf4efcb
```

The runs need the [prebuilt images](/concepts/runner-backends#prebuilt-images) of the
task and agent under `runs.registry`, where the nodes can pull them.

### On kind

`just verify kind` does this on your machine, and the Helm workflow does it every week and for every release. The images are built from the
checkout and loaded into the nodes, so the chart uses them as they are:

```sh
kind create cluster --name ssebench --config deploy/k8s/kind.yaml
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.31.0/manifests/calico.yaml
kubectl -n kube-system rollout status daemonset/calico-node

kind load docker-image --name ssebench \
  "$R/litellm:$V" "$R/catalog:$V" "$R/webui:$V" postgres:16 \
  "$R/agent-reference/gjson-196-bf4efcb:$V"       # R: your SSEBENCH_REGISTRY, V: the version

kubectl create namespace ssebench-runs
helm install ssebench deploy/helm/ssebench --create-namespace -n ssebench --wait \
  --set image.registry=$R --set image.pullPolicy=Never --set runs.imagePullPolicy=Never \
  --set runs.namespace=ssebench-runs
```

The proxy starts without a provider key, and answers the runner's key requests. It
cannot reach a model, so use the `reference` agent, or the `dummy` agent whose patch
fails on purpose.

### The web UI

By default the web UI is a **read-only viewer** (`webui.hosted=true`): it lists the runs
in the runs' namespace and shows their dialogs, diffs, logs and grades, and it refuses to
launch, stop or remove a run, opens no terminal and no assistant, and holds no key of
the proxy. Set `webui.hosted=false` to let it launch runs from the browser: it then runs
`ssebench run --backend kubernetes --prebuilt` with its service account, against the
catalog in the release, and a launch spends the provider keys of the proxy. The launcher
offers the models and agents of the image and the tasks of the catalog.

The web UI listens on all addresses of its pod, so it needs its token: the chart
makes one, and every request needs it. The chart does not open the web UI to the network:
its Service is a `ClusterIP`. To reach it from outside the cluster, set
`ingress.enabled=true` with a host, and put TLS in front, since the token
travels in clear text over plain HTTP; the [security model](/webui/security) has the rest.
A proxy that changes the `Host` header needs `webui.corsOrigins`.

### Values

`helm show values` prints the defaults with their comments. All of the values:

| Value | Default | Meaning |
|---|---|---|
| `image.registry` | `ghcr.io/42-b3yond-6ug/ssebench` | Registry of the chart's images, `<registry>/<name>:<tag>` |
| `image.tag` | the chart's `appVersion` | Tag of every image; the versions of the chart and of the images are one |
| `image.pullPolicy` | `IfNotPresent` | `imagePullPolicy` of the chart's containers |
| `image.pullSecrets` | none | Image pull Secrets for the chart's pods |
| `auth.existingSecret` | none | A Secret of yours with `LITELLM_MASTER_KEY` (starts with `sk-`), `POSTGRES_PASSWORD` (letters and digits) and `SSEBENCH_WEBUI_TOKEN` (16 or more characters, no spaces). Without it the chart makes a Secret with random values and keeps them on upgrade. Use your own when a tool renders the chart without a cluster to look at, as a GitOps controller can, since it would make new values on each render |
| `litellm.image.name`, `litellm.image.tag` | `litellm`, empty | The proxy's image; an empty tag is `image.tag` |
| `litellm.providerKeySecrets` | none | Secrets whose entries become the proxy's environment: the provider keys, by the names the models use (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`) |
| `litellm.config` | none | A LiteLLM configuration that replaces the one in the image, which lists `models/`. It must set `master_key: os.environ/LITELLM_MASTER_KEY` |
| `litellm.resources` | 100m CPU and 512Mi to 2Gi | Requests and limits of the proxy |
| `postgres.enabled` | `true` | `false` uses your own database instead of the chart's |
| `postgres.image` | `postgres:16` | The database's image |
| `postgres.persistence.enabled`, `postgres.persistence.size`, `postgres.persistence.storageClass` | `true`, `5Gi`, cluster default | The database's volume. Without persistence the keys of the runs are lost when its pod restarts |
| `postgres.resources` | 50m CPU and 128Mi to 1Gi | Requests and limits of the database |
| `postgres.externalSecret` | none | With `postgres.enabled=false`: a Secret with `DATABASE_URL`, a PostgreSQL URL of the database |
| `catalog.image.name`, `catalog.image.tag` | `catalog`, empty | The catalog's image, which carries the manifest of the `pilot` dataset |
| `catalog.resources` | 10m CPU and 32Mi to 128Mi | Requests and limits of the catalog |
| `webui.image.name`, `webui.image.tag` | `webui`, empty | The web UI's image |
| `webui.hosted` | `true` | The web UI as a read-only viewer; `false` lets it launch runs |
| `webui.terminal` | `false` | With `webui.hosted=false`: a shell in the run pods (`SSEBENCH_WEBUI_TERMINAL`) |
| `webui.corsOrigins` | none | Origins besides its own that may call its API (`SSEBENCH_WEBUI_CORS_ORIGINS`) |
| `webui.persistence.enabled`, `webui.persistence.size`, `webui.persistence.storageClass` | `false`, `5Gi`, cluster default | A volume for the results of launched runs, under `/app/results`. Without it an `emptyDir` holds them until the pod is replaced |
| `webui.service.type`, `webui.service.port` | `ClusterIP`, `3001` | The web UI's Service |
| `webui.resources` | 100m CPU and 256Mi to 1Gi | Requests and limits of the web UI |
| `runs.namespace` | the release's namespace | Where the runs' Jobs go, and where the Role is bound. It must exist. Use a namespace of its own: see [RBAC](#rbac) |
| `runs.registry` | `image.registry` | Registry of the prebuilt agent images, `SSEBENCH_REGISTRY` |
| `runs.egress` | `restricted` | What a run's pod may reach when a launch does not say (`SSEBENCH_EGRESS`); see [Egress](#egress) |
| `runs.runtimeClassName` | none | `runtimeClassName` of the run pods, for gVisor or Kata Containers (`SSEBENCH_K8S_RUNTIME_CLASS`) |
| `runs.imagePullPolicy`, `runs.imagePullSecrets` | `IfNotPresent`, none | Pull policy and pull Secrets of the run pods (`SSEBENCH_K8S_IMAGE_PULL_POLICY`, `SSEBENCH_K8S_IMAGE_PULL_SECRETS`); the Secrets must be in the runs' namespace |
| `runs.resources` | the backend's | `requests` and `limits` of a run's task container (`SSEBENCH_K8S_RESOURCES`). Empty is 1 CPU and 2Gi to 4 CPUs and 8Gi. A value replaces both |
| `runs.ttlSecondsAfterFinished`, `runs.deadlineSlackSeconds` | `3600`, `1800` | `SSEBENCH_K8S_TTL_SECONDS` and `SSEBENCH_K8S_DEADLINE_SLACK` |
| `rbac.create` | `true` | The Role and RoleBinding. Without them, bind a Role of your own to the service account |
| `serviceAccount.name`, `serviceAccount.annotations` | the release's name, none | The web UI's service account, for example to add a cloud identity |
| `networkPolicy.enabled` | `true` | The NetworkPolicies of the proxy and the database |
| `networkPolicy.proxyExtraIngress` | none | More peers that may reach the proxy, as NetworkPolicy `from` entries: a monitoring namespace, or pods of yours that run `ssebench` in the cluster |
| `ingress.enabled`, `ingress.className`, `ingress.annotations`, `ingress.hosts`, `ingress.tls` | `false`, and none | An Ingress for the web UI; `hosts` are `host`, `path` and `pathType` |
| `nameOverride`, `fullnameOverride` | none | The names of the objects, which start with the release's name |
| `nodeSelector`, `tolerations`, `affinity`, `podAnnotations` | none | Scheduling and annotations of the chart's own pods (not the runs') |

### Upgrade and uninstall

`helm upgrade` keeps the Secret with the keys and the database's volume. It replaces
the pods whose settings changed, and replacing the web UI's pod ends the
`ssebench run` processes of the launches in progress. The Job of a run that has started
stays: a run launched from the web UI is kept until it is stopped and removed there, or
with `kubectl delete job,secret,networkpolicy -n <runs namespace> -l ssebench.run-id=<id>`.

`helm uninstall` removes the release's objects. It leaves the database's volume (the
volumes of a StatefulSet stay), the namespaces and the runs' Jobs, which the chart did
not create.

### Security notes for the chart

- **Enforce NetworkPolicy, or the policies do nothing.** This applies to the
  runs' [egress policies](#egress) and to the chart's own two policies. A cluster
  whose network plugin ignores them gives a `restricted` run the internet. Test the
  cluster once as described under [Egress](#egress).
- **The web UI's service account can run commands in every pod of the runs'
  namespace.** That is `pods/exec` in the [Role](#rbac), and it is how results are
  read out. A separate namespace for the runs keeps this from reaching the proxy, the
  database and their Secrets, which sit in the release's namespace.
  The read-only viewer needs most of the Role as well, to reach the runs' daemons,
  so `webui.hosted=true` does not shrink it.
- **The token and the master key are in a Secret, and the pods of the release read
  them.** Restrict `get secrets` in the release's namespace. The provider keys are only in
  the proxy's pod, and the run pods get a key of their own, limited to the run's model and a
  budget, not the master key or a provider key.
- **The proxy accepts only the web UI and the run pods.** Anyone else in the cluster is
  refused, including the pods of other namespaces, but the Secret's master key gives
  access to everything on the proxy. `kubectl port-forward` reaches it through the API
  server and the kubelet, which the policy does not restrict.
- **`webui.hosted=false` lets anyone with the token spend your provider keys.** Give
  the token to people you trust to do that. Prefer the read-only viewer for anything
  shared.
- **The web UI runs as root without capabilities**, as its image does, and has no host
  access. The proxy also runs as root, because its image does. The database and the
  catalog run as unprivileged users. None of them is privileged, and none has a
  service account token except the web UI.
- **Pin the images by digest** with `image.tag` set to `<version>@sha256:...` if you
  need a deployment that cannot change under you.

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
The Helm chart creates the same rules, in the namespace `runs.namespace`, and binds
them to the web UI's service account.

| Resource | Verbs | For |
|---|---|---|
| `jobs` | create, get, list, delete | The run |
| `pods` | create, get, list, delete | Following the run, and the short pod that copies the reference patch out of an image |
| `pods/log` | get | The run's output |
| `pods/exec` | create, get | Reading the results out, and stopping the task container. `get` is for clusters before 1.30 |
| `pods/portforward` | create, get | `ssebench runs endpoint` only |
| `secrets` | create, patch, delete | The run's environment, and its owner reference |
| `networkpolicies` | create, patch, delete | The run's network policy, and its owner reference |

`pods/exec` is the powerful one: it runs commands in any pod of the namespace. Give
the runs a namespace of their own, and do not bind the role in a namespace that holds
anything else. A `ssebench` process inside the cluster uses the same role through the
pod's service account.

## Watching runs

`ssebench runs list`, `inspect`, `logs`, `stop`, `remove`, `endpoint` and `exec`
(what the [web UI](/webui/) calls) work on Jobs the same way as on containers, with
`--backend kubernetes`. They find a run by its `ssebench.run-id` label, and report
the Job's creation time as `created_at`.

- **`endpoint`** prints a URL on `127.0.0.1`. It starts a detached
  `kubectl port-forward` to the run's pod on a local port of its own, records it in a
  file in the system's temporary directory, and reuses it on later calls for the same
  pod and port; it outlives the command and ends with the pod or with
  `ssebench runs remove`. It is a forward and not a Service because the run's network
  policy admits no ingress, which a forward, going through the API server and the
  kubelet, does not pass. Anyone on the machine can connect to the port, as with a
  Docker container's address. It needs `kubectl` on the PATH and the
  `pods/portforward` permission.
- **`exec`** is `kubectl exec` in the task container, with `--user` done by `su` and
  `--workdir` by `cd`. It cannot pass `--env` variables, since `kubectl exec` has no way
  to take a value from the environment without showing it in the process list; a
  command that asks for them fails. The web UI's terminal works; its assistant, which
  passes its provider configuration that way, does not start on this backend yet.

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
- `runs endpoint` and `runs exec` need `kubectl`. The web UI's assistant does not work, since it needs `runs exec --env`.

## Next steps

- [Web UI](/webui/) and its [security model](/webui/security)
- [Runner backends](/concepts/runner-backends): the interface this backend implements
- [Integrity and egress](/deployment/integrity-and-egress)
- [Integrity model](/concepts/integrity)
- [LiteLLM proxy](/concepts/litellm-proxy)
