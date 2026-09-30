"""The Kubernetes backend, against an in-memory cluster: the objects it creates, how it follows a run and reads its results."""

import base64
import io
import tarfile
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from ssebench.agents import Agent
from ssebench.backends import (
    ARCHIVE_PATH,
    RESULTS_PATH,
    RUN_ID_LABEL,
    BackendError,
    ImageRequest,
    ImageUnavailableError,
    Mount,
    NetworkPolicy,
    RunHandle,
    RunSpec,
    SidecarPair,
)
from ssebench.backends.kubernetes import KubernetesBackend, KubernetesConfig, KubernetesRun, manifests
from ssebench.backends.kubernetes import backend as backend_module
from ssebench.backends.kubernetes.api import KubeError
from ssebench.errors import UserError
from ssebench.tasks import LocalTask

from .fake_kube import FakeKube, running, tar_bytes, terminated, waiting

RUN = "20260101-abc123"
IMAGE = "registry.test/ssebench/agent-reference/demo-1:1.0.0"
GRADE = b'{"patch_result": {"status": "passed"}}'


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Poll quickly, and end the log forwarders that a test leaves behind."""
    monkeypatch.setattr(backend_module, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(backend_module, "LOG_JOIN_SECONDS", 5.0)
    started: list[KubernetesRun] = []
    real_start = KubernetesBackend.start

    def start(self: KubernetesBackend, spec: RunSpec) -> RunHandle:
        handle = real_start(self, spec)
        assert isinstance(handle, KubernetesRun)
        started.append(handle)
        return handle

    monkeypatch.setattr(KubernetesBackend, "start", start)
    yield
    for handle in started:
        handle.finished.set()
        if handle.forwarder is not None:
            handle.forwarder.join(5)


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, "demo-1")
    return LocalTask("demo-1", dataset)


@pytest.fixture
def kube() -> FakeKube:
    return FakeKube()


@pytest.fixture
def backend(kube: FakeKube) -> KubernetesBackend:
    return KubernetesBackend(KubernetesConfig(), api=kube)


def make_spec(tmp_path: Path, **changes: Any) -> RunSpec:
    fields: dict[str, Any] = {
        "run_id": RUN,
        "mode": "sandbox",
        "task_name": "demo-1",
        "image": IMAGE,
        "env": {"SSE_API_KEY": "sk-secret-key", "SSE_BASE_URL": "http://litellm:4000", "TIMEOUT": "600"},
        "results": Mount(source=str(tmp_path / "run"), target=RESULTS_PATH),
        "archive": Mount(source=str(tmp_path / "run" / "archive"), target=ARCHIVE_PATH),
        "network": NetworkPolicy(),
        "labels": {
            "ssebench.run-id": RUN,
            "ssebench.task-id": "demo-1",
            "ssebench.agent": "reference",
            "ssebench.model": "none",
            "ssebench.webui": "true",
            "ssebench.results": str(tmp_path / "run"),
        },
        "timeout": 600,
    }
    fields.update(changes)
    return RunSpec(**fields)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """The run directory as the runner leaves it before the run: an archive and an empty result.json."""
    path = tmp_path / "run"
    (path / "archive").mkdir(parents=True)
    (path / "result.json").touch()
    return path


def job_of(kube: FakeKube) -> dict[str, Any]:
    return next(obj for (kind, _), obj in kube.objects.items() if kind == "job")


def container(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in job["spec"]["template"]["spec"]["containers"] if c["name"] == name)


# ==================== the objects of a run ====================


def test_a_run_is_a_job_with_a_secret_and_a_network_policy_created_in_that_order(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    handle = backend.start(make_spec(tmp_path))

    assert [call[1] for call in kube.calls if call[0] == "create"] == ["networkpolicy", "secret", "job"]
    assert handle.name == manifests.object_name(RUN) == "ssebench-20260101-abc123"
    job = job_of(kube)
    owner = {"apiVersion": "batch/v1", "kind": "Job", "name": handle.name, "uid": job["metadata"]["uid"]}
    for kind in ("secret", "networkpolicy"):
        references = kube.objects[(kind, handle.name)]["metadata"]["ownerReferences"]
        assert [{k: v for k, v in ref.items() if k in owner} for ref in references] == [owner]


def test_the_job_runs_once_with_a_deadline_from_the_timeout_and_a_time_to_live(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path, timeout=600))

    spec = job_of(kube)["spec"]
    assert spec["backoffLimit"] == 0
    assert spec["activeDeadlineSeconds"] == 600 + KubernetesConfig().deadline_slack
    assert spec["ttlSecondsAfterFinished"] == KubernetesConfig().ttl_seconds
    assert spec["template"]["spec"]["restartPolicy"] == "Never"


def test_a_kept_run_has_no_time_to_live(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    _ = backend.start(make_spec(tmp_path, keep=True))

    assert "ttlSecondsAfterFinished" not in job_of(kube)["spec"]


def test_the_task_container_is_root_without_privilege_and_keeps_six_capabilities(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path))

    job = job_of(kube)
    pod = job["spec"]["template"]["spec"]
    context = container(job, "task")["securityContext"]
    assert context["privileged"] is False
    assert context["allowPrivilegeEscalation"] is False
    assert context["runAsUser"] == 0
    assert context["capabilities"]["drop"] == ["ALL"]
    assert sorted(context["capabilities"]["add"]) == ["CHOWN", "DAC_OVERRIDE", "FOWNER", "KILL", "SETGID", "SETUID"]
    assert pod["securityContext"] == {"seccompProfile": {"type": "RuntimeDefault"}}
    assert not any(pod.get(host) for host in ("hostNetwork", "hostPID", "hostIPC", "shareProcessNamespace"))
    assert pod["automountServiceAccountToken"] is False
    assert not any("hostPath" in volume for volume in pod["volumes"])


def test_the_collector_can_read_but_not_write_the_results(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path))

    collector = container(job_of(kube), "collector")
    assert collector["securityContext"]["capabilities"] == {"drop": ["ALL"], "add": ["DAC_READ_SEARCH"]}
    mounts = {m["mountPath"]: m.get("readOnly", False) for m in collector["volumeMounts"]}
    assert mounts[manifests.COLLECTOR_RESULTS] and mounts[manifests.COLLECTOR_ARCHIVE]
    assert collector["image"] == IMAGE


def test_the_environment_is_in_a_secret_and_not_in_the_job(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    handle = backend.start(make_spec(tmp_path))

    secret = kube.objects[("secret", handle.name)]
    assert base64.b64decode(secret["data"]["SSE_API_KEY"]) == b"sk-secret-key"
    assert container(job_of(kube), "task")["envFrom"] == [{"secretRef": {"name": handle.name}}]
    assert "sk-secret-key" not in str(job_of(kube))
    assert "sk-secret-key" not in repr(make_spec(tmp_path))


def test_the_reference_patch_is_a_read_only_file_from_the_secret(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    patch = tmp_path / "patch.diff"
    _ = patch.write_text("diff --git a/f b/f\n")
    spec = make_spec(tmp_path, artifacts=(Mount(source=str(patch), target="/reference/patch.diff", read_only=True),))

    handle = backend.start(spec)

    assert base64.b64decode(kube.objects[("secret", handle.name)]["data"]["artifact-0"]) == b"diff --git a/f b/f\n"
    mounts = container(job_of(kube), "task")["volumeMounts"]
    assert {"name": "files", "mountPath": "/reference/patch.diff", "subPath": "artifact-0", "readOnly": True} in mounts
    files = next(v for v in job_of(kube)["spec"]["template"]["spec"]["volumes"] if v["name"] == "files")
    assert files["secret"]["defaultMode"] == 0o444


def test_a_run_without_artifacts_has_no_files_volume(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path))

    volumes = job_of(kube)["spec"]["template"]["spec"]["volumes"]
    assert [v["name"] for v in volumes] == ["results", "archive", "control"]


def test_labels_are_on_the_job_and_pod_and_the_results_path_is_an_annotation(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    handle = backend.start(make_spec(tmp_path))

    job = job_of(kube)
    pod_template = job["spec"]["template"]["metadata"]
    for labels in (job["metadata"]["labels"], pod_template["labels"]):
        assert labels[RUN_ID_LABEL] == RUN
        assert labels["ssebench.task-id"] == "demo-1"
        assert labels["ssebench.agent"] == "reference"
        assert labels["app.kubernetes.io/managed-by"] == "ssebench"
        assert "ssebench.results" not in labels
    assert job["metadata"]["annotations"]["ssebench.results"] == str(tmp_path / "run")
    assert handle.run_id == RUN


def test_resources_runtime_class_and_pull_secrets_come_from_the_configuration(tmp_path: Path, kube: FakeKube) -> None:
    config = KubernetesConfig(
        runtime_class="gvisor",
        image_pull_secrets=("registry-login",),
        image_pull_policy="Always",
        resources={"requests": {"cpu": "500m"}, "limits": {"memory": "1Gi"}},
    )

    _ = KubernetesBackend(config, api=kube).start(make_spec(tmp_path))

    job = job_of(kube)
    pod = job["spec"]["template"]["spec"]
    assert pod["runtimeClassName"] == "gvisor"
    assert pod["imagePullSecrets"] == [{"name": "registry-login"}]
    task = container(job, "task")
    assert task["imagePullPolicy"] == "Always"
    assert task["resources"] == {"requests": {"cpu": "500m"}, "limits": {"memory": "1Gi"}}


def test_the_default_resources_are_requests_below_limits(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path))

    resources = container(job_of(kube), "task")["resources"]
    assert set(resources["requests"]) == set(resources["limits"]) == {"cpu", "memory", "ephemeral-storage"}
    assert "runtimeClassName" not in job_of(kube)["spec"]["template"]["spec"]


@pytest.mark.parametrize("run_id", ["Run_1.A", "x" * 64, "20260101-abc123"])
def test_object_names_are_dns_labels_and_distinct_for_distinct_run_ids(run_id: str) -> None:
    name = manifests.object_name(run_id)

    assert len(name) <= 63 and name == name.lower()
    assert name.replace("-", "").isalnum() and not name.endswith("-")


def test_two_run_ids_that_differ_in_case_get_different_names() -> None:
    assert manifests.object_name("Run") != manifests.object_name("run")


# ==================== the network ====================


def policy_of(kube: FakeKube) -> dict[str, Any]:
    return next(obj for (kind, _), obj in kube.objects.items() if kind == "networkpolicy")


def test_the_restricted_policy_allows_dns_and_the_proxy_and_denies_ingress(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path))

    spec = policy_of(kube)["spec"]
    assert spec["podSelector"] == {"matchLabels": {RUN_ID_LABEL: RUN}}
    assert spec["policyTypes"] == ["Ingress", "Egress"]
    assert "ingress" not in spec
    dns, proxy = spec["egress"]
    assert dns["to"][0]["podSelector"] == {"matchLabels": {"k8s-app": "kube-dns"}}
    assert {p["port"] for p in dns["ports"]} == {53}
    assert proxy["to"][0]["namespaceSelector"]["matchLabels"] == {"kubernetes.io/metadata.name": "runs"}
    assert proxy["to"][0]["podSelector"] == {"matchLabels": {"app.kubernetes.io/name": "litellm"}}
    assert proxy["ports"] == [{"protocol": "TCP", "port": 4000}]
    assert len(spec["egress"]) == 2


def test_the_open_policy_adds_the_internet_but_not_the_private_ranges(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    _ = backend.start(make_spec(tmp_path, network=NetworkPolicy(egress="open")))

    egress = policy_of(kube)["spec"]["egress"]
    assert len(egress) == 3
    block = egress[2]["to"][0]["ipBlock"]
    assert block["cidr"] == "0.0.0.0/0"
    assert {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"} <= set(block["except"])


def test_the_policy_follows_the_proxy_configuration(tmp_path: Path, kube: FakeKube) -> None:
    config = KubernetesConfig(
        proxy_namespace="ssebench-system",
        proxy_selector={"app": "llm"},
        proxy_service_url="http://llm.ssebench-system.svc:8080",
    )

    _ = KubernetesBackend(config, api=kube).start(make_spec(tmp_path))

    proxy = policy_of(kube)["spec"]["egress"][1]
    assert proxy["to"][0]["namespaceSelector"]["matchLabels"] == {"kubernetes.io/metadata.name": "ssebench-system"}
    assert proxy["to"][0]["podSelector"] == {"matchLabels": {"app": "llm"}}
    assert proxy["ports"] == [{"protocol": "TCP", "port": 8080}]


def test_the_proxy_endpoint_is_the_service_in_the_cluster_and_localhost_outside(
    monkeypatch: pytest.MonkeyPatch, backend: KubernetesBackend
) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setenv("LITELLM_PORT", "4711")

    endpoint = backend.proxy()

    assert endpoint.service_url == "http://litellm.runs.svc:4000"
    assert endpoint.host_url == "http://localhost:4711"

    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    assert backend.proxy().host_url == "http://litellm.runs.svc:4000"


# ==================== starting ====================


def test_a_failed_start_removes_what_was_created(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    kube.fail["create job"] = KubeError("forbidden: cannot create jobs", 403)

    with pytest.raises(BackendError, match="Could not start the run .*forbidden: cannot create jobs"):
        _ = backend.start(make_spec(tmp_path))

    assert kube.objects == {}


def test_a_taken_name_is_reported_as_such(tmp_path: Path, backend: KubernetesBackend) -> None:
    _ = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match="taken by another run"):
        _ = backend.start(make_spec(tmp_path))


def test_an_unreadable_file_for_the_run_is_a_backend_error(tmp_path: Path, backend: KubernetesBackend) -> None:
    spec = make_spec(tmp_path, artifacts=(Mount(source=str(tmp_path / "missing"), target="/x", read_only=True),))

    with pytest.raises(BackendError, match="Cannot read a file for the run"):
        _ = backend.start(spec)


def test_sidecar_mode_is_refused_with_a_reason(tmp_path: Path, backend: KubernetesBackend, task: LocalTask) -> None:
    pair = SidecarPair(task_name="demo-1", source_dir="/src/demo", environment_image="env", difficulty=2)
    spec = make_spec(tmp_path, mode="sidecar", sidecar=pair)

    with pytest.raises(BackendError, match="Sidecar mode is not supported"):
        _ = backend.start(spec)
    request = ImageRequest(mode="sidecar", task=task, agent=Agent("dummy", task_name="sidecar"), prebuilt=True)
    with pytest.raises(UserError, match="Sidecar mode is not supported"):
        _ = backend.prepare_images(request)


def test_the_backend_cannot_build_images(backend: KubernetesBackend, task: LocalTask) -> None:
    request = ImageRequest(mode="sandbox", task=task, agent=Agent("dummy", task_name=task.name))

    with pytest.raises(UserError, match="prebuilt"):
        _ = backend.prepare_images(request)
    assert backend.builds_images is False


def test_prebuilt_images_are_named_and_the_cluster_is_checked(
    backend: KubernetesBackend, task: LocalTask, kube: FakeKube
) -> None:
    request = ImageRequest(mode="sandbox", task=task, agent=Agent("dummy", task_name=task.name), prebuilt=True)

    images = backend.prepare_images(request)

    assert images.agent == request.agent.image_name
    kube.fail["find job"] = KubeError("forbidden: cannot list jobs", 403)
    with pytest.raises(ImageUnavailableError, match="Cannot use the cluster .*forbidden"):
        _ = backend.prepare_images(request)


def test_a_missing_client_library_is_reported_with_the_way_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backend_module, "find_spec", lambda name: None)

    with pytest.raises(BackendError, match=r"pip install 'ssebench\[kubernetes\]'"):
        _ = KubernetesBackend(KubernetesConfig())


# ==================== waiting and output ====================


def test_wait_returns_the_exit_status_of_the_task_container_and_forwards_its_output(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, capsys: pytest.CaptureFixture[str]
) -> None:
    kube.task = terminated(3)
    handle = backend.start(make_spec(tmp_path))

    assert backend.wait(handle) == 3

    assert capsys.readouterr().out == "first line\nsecond line\n"


def test_wait_follows_a_pod_from_pending_to_exit(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = iter([waiting(), running(), running()])

    def sleep(seconds: float) -> None:
        kube.task = next(states, terminated(0))

    monkeypatch.setattr(backend_module, "time", SimpleNamespace(monotonic=backend_module.time.monotonic, sleep=sleep))
    handle = backend.start(make_spec(tmp_path))

    assert backend.wait(handle) == 0


def test_wait_times_out_while_the_run_is_going(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    kube.task = running()
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(TimeoutError, match="still running"):
        _ = backend.wait(handle, timeout=0.05)
    backend.cleanup(handle)


def test_a_container_that_cannot_start_fails_the_run_with_the_reason(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    kube.task = waiting("CreateContainerConfigError", 'secret "x" not found')
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match=r"cannot start: CreateContainerConfigError: secret \"x\" not found"):
        _ = backend.wait(handle)
    backend.cleanup(handle)


def test_an_image_that_cannot_be_pulled_fails_the_run_after_a_while(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend_module, "IMAGE_PULL_PATIENCE", 0.0)
    kube.task = waiting("ImagePullBackOff", "Back-off pulling image")
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match="Cannot pull the image of the run: ImagePullBackOff"):
        _ = backend.wait(handle)
    backend.cleanup(handle)


def test_a_pod_that_never_starts_fails_the_run_with_the_scheduler_message(tmp_path: Path, kube: FakeKube) -> None:
    kube.pod_conditions = [
        {"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": "0/1 nodes: Insufficient cpu"}
    ]
    backend = KubernetesBackend(KubernetesConfig(start_timeout=0), api=kube)
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(
        BackendError, match="did not start within 0 seconds: Unschedulable: 0/1 nodes: Insufficient cpu"
    ):
        _ = backend.wait(handle)
    backend.cleanup(handle)


def test_a_pod_the_cluster_removed_after_the_deadline_is_an_error_not_a_hang(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    kube.task = running()
    handle = backend.start(make_spec(tmp_path))
    del kube.objects[("pod", f"{handle.name}-abcde")]
    kube.job_conditions = [{"type": "Failed", "status": "True", "reason": "DeadlineExceeded", "message": "too long"}]

    with pytest.raises(BackendError, match="failed before it ran: DeadlineExceeded: too long"):
        _ = backend.wait(handle)


def test_lost_api_calls_are_retried_and_then_reported(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    kube.task = running()
    handle = backend.start(make_spec(tmp_path))
    kube.fail["find pod"] = KubeError("connection refused")

    with pytest.raises(BackendError, match="Lost the cluster while waiting .*connection refused"):
        _ = backend.wait(handle)


def test_logs_are_the_task_containers_lines(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    kube.task = terminated(0)
    handle = backend.start(make_spec(tmp_path))

    assert list(backend.logs(handle)) == ["first line", "second line"]


# ==================== results ====================


def test_results_come_from_the_results_volume_and_the_archive_from_the_archive_volume(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    kube.task = terminated(0)
    kube.volumes["/results"] = {"result.json": GRADE, "logs/daemon.log": b"log\n"}
    kube.volumes["/archive"] = {"dialog.jsonl": b"{}\n"}
    handle = backend.start(make_spec(tmp_path))
    _ = backend.wait(handle)

    backend.collect_results(handle, run_dir)

    assert (run_dir / "result.json").read_bytes() == GRADE
    assert (run_dir / "logs" / "daemon.log").read_bytes() == b"log\n"
    assert (run_dir / "archive" / "dialog.jsonl").read_bytes() == b"{}\n"
    assert kube.released, "the collector should be told to exit"


def test_a_result_json_in_the_archive_cannot_stand_in_for_the_grade(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    kube.task = terminated(0)
    kube.volumes["/results"] = {"result.json": GRADE}
    kube.volumes["/archive"] = {"result.json": b'{"patch_result": {"status": "forged"}}', "../result.json": b"forged"}
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match="outside the results"):
        backend.collect_results(handle, run_dir)

    assert (run_dir / "result.json").read_bytes() == GRADE
    assert not (run_dir.parent / "result.json").exists()


def test_a_link_in_the_archive_is_not_unpacked(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        link = tarfile.TarInfo("evil")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
        note = tarfile.TarInfo("note.txt")
        note.size = 2
        tar.addfile(note, io.BytesIO(b"ok"))
    kube.task = terminated(0)
    kube.volumes["/results"] = {"result.json": GRADE}
    kube.volumes["/archive"] = buffer.getvalue()
    handle = backend.start(make_spec(tmp_path))

    backend.collect_results(handle, run_dir)

    assert not (run_dir / "archive" / "evil").exists() and not (run_dir / "archive" / "evil").is_symlink()
    assert (run_dir / "archive" / "note.txt").read_bytes() == b"ok"


def test_a_truncated_tar_stream_is_an_error(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    kube.task = terminated(0)
    kube.volumes["/results"] = tar_bytes({"result.json": GRADE * 100})[:700]
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match="not a valid archive"):
        backend.collect_results(handle, run_dir)


def test_results_that_are_gone_are_an_error(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    kube.task = terminated(0)
    kube.collector = terminated(0)
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match="no longer in the cluster"):
        backend.collect_results(handle, run_dir)


def test_a_failing_exec_is_a_backend_error(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    kube.task = terminated(0)
    kube.fail["exec pod"] = KubeError("exec in pod exited with status 2: tar: nope")
    handle = backend.start(make_spec(tmp_path))

    with pytest.raises(BackendError, match="Could not read the results .*tar: nope"):
        backend.collect_results(handle, run_dir)


# ==================== stopping and cleaning up ====================


def test_stop_sends_sigterm_to_the_task_containers_first_process_and_keeps_the_pod(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    kube.task = running()
    handle = backend.start(make_spec(tmp_path))

    backend.stop(handle, grace=5)

    assert kube.execs[-1][-1] == "kill -TERM 1"
    assert ("delete", "job", handle.name) not in kube.calls
    assert backend.wait(handle) == 143


def test_stop_deletes_the_job_when_the_container_ignores_sigterm(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    kube.task = running()
    kube.ignore_term = True
    handle = backend.start(make_spec(tmp_path))

    backend.stop(handle, grace=0)

    assert ("delete", "job", handle.name) in kube.calls
    assert backend.wait(handle) == 143


def test_stop_before_the_container_started_deletes_the_job(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path
) -> None:
    handle = backend.start(make_spec(tmp_path))

    backend.stop(handle)

    assert ("delete", "job", handle.name) in kube.calls
    assert backend.wait(handle) == 143
    backend.collect_results(handle, run_dir)  # nothing to collect, and no error


def test_stop_on_a_finished_run_does_nothing(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    kube.task = terminated(0)
    handle = backend.start(make_spec(tmp_path))

    backend.stop(handle)

    assert kube.execs == []


def test_cleanup_removes_the_run_and_keep_leaves_it(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    kube.task = terminated(0)
    kept = backend.start(make_spec(tmp_path, run_id="kept", keep=True))
    removed = backend.start(make_spec(tmp_path))

    backend.cleanup(removed)
    backend.cleanup(kept)

    assert {kind for kind, name in kube.objects if name.startswith(kept.name)} >= {"job", "secret", "networkpolicy"}
    assert not any(name.startswith(removed.name) for _, name in kube.objects)
    assert kube.released, "a kept run lets its collector go"


# ==================== finding runs ====================


def test_list_runs_reports_state_exit_code_and_labels(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube
) -> None:
    kube.task = terminated(7)
    first = backend.start(make_spec(tmp_path))
    kube.task = terminated(0)
    _ = backend.start(make_spec(tmp_path, run_id="second", labels={"ssebench.task-id": "other"}))

    runs = backend.list_runs()
    info = backend.inspect_run(RUN)

    assert sorted(r.run_id for r in runs) == sorted([RUN, "second"])
    assert info is not None and info.state == "exited" and info.exit_code == 0
    assert info.handle.name == first.name and info.image == IMAGE
    assert info.labels["ssebench.results"] == str(tmp_path / "run")


def test_list_runs_filters_on_labels_and_on_values_kubernetes_holds_as_annotations(
    tmp_path: Path, backend: KubernetesBackend
) -> None:
    _ = backend.start(make_spec(tmp_path))
    _ = backend.start(make_spec(tmp_path, run_id="second", labels={"ssebench.task-id": "other"}))

    assert [r.run_id for r in backend.list_runs({"ssebench.task-id": "other"})] == ["second"]
    assert [r.run_id for r in backend.list_runs({"ssebench.results": str(tmp_path / "run")})] == [RUN]
    assert backend.list_runs({"ssebench.task-id": "none"}) == []
    assert backend.inspect_run("missing") is None


def test_a_found_run_can_be_stopped_and_cleaned_up(tmp_path: Path, backend: KubernetesBackend, kube: FakeKube) -> None:
    kube.task = running()
    _ = backend.start(make_spec(tmp_path))
    info = backend.inspect_run(RUN)
    assert info is not None and info.state == "running"

    backend.stop(info.handle, grace=5)
    backend.cleanup(info.handle)

    assert kube.execs[-1][-1] == "kill -TERM 1"
    assert backend.list_runs() == []


# ==================== copying a file out of an image ====================


def test_copy_from_image_runs_a_pod_and_removes_it(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"diff --git a/f b/f\n" * 400
    encoded = base64.encodebytes(content).decode().splitlines()

    kube.pod_phase = "Succeeded"
    monkeypatch.setattr(kube, "pod_log", lambda pod, container, **kw: iter(encoded))
    dest = tmp_path / "patch.diff"

    backend.copy_from_image(IMAGE, PurePosixPath("/ssebench/diffs/patch.diff"), dest)

    assert dest.read_bytes() == content
    assert not kube.objects
    assert ("create", "pod", kube.calls[0][2]) == kube.calls[0]


def test_copy_from_image_reports_a_failed_pod(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, monkeypatch: pytest.MonkeyPatch
) -> None:
    kube.pod_phase = "Failed"

    with pytest.raises(RuntimeError, match="Could not copy /x from .*: the pod failed"):
        backend.copy_from_image(IMAGE, PurePosixPath("/x"), tmp_path / "out")

    assert not kube.objects


# ==================== configuration ====================


def test_settings_configure_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "SSEBENCH_K8S_NAMESPACE": "bench",
        "SSEBENCH_K8S_RUNTIME_CLASS": "kata",
        "SSEBENCH_K8S_IMAGE_PULL_SECRETS": "a, b",
        "SSEBENCH_K8S_PROXY_SELECTOR": "app=llm,tier=proxy",
        "SSEBENCH_K8S_RESOURCES": '{"requests": {"cpu": 2}, "limits": {"memory": "4Gi"}}',
        "SSEBENCH_K8S_TTL_SECONDS": "60",
        "SSEBENCH_K8S_DEADLINE_SLACK": "90",
    }.items():
        monkeypatch.setenv(name, value)

    config = KubernetesConfig.from_settings()

    assert config.namespace == "bench" and config.runtime_class == "kata"
    assert config.image_pull_secrets == ("a", "b")
    assert dict(config.proxy_selector) == {"app": "llm", "tier": "proxy"}
    assert config.resources == {"requests": {"cpu": "2"}, "limits": {"memory": "4Gi"}}
    assert (config.ttl_seconds, config.deadline_slack) == (60, 90)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SSEBENCH_K8S_TTL_SECONDS", "soon"),
        ("SSEBENCH_K8S_RESOURCES", "[1, 2]"),
        ("SSEBENCH_K8S_RESOURCES", '{"request": {}}'),
        ("SSEBENCH_K8S_PROXY_SELECTOR", "nonsense"),
    ],
)
def test_a_malformed_setting_is_a_user_error(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(UserError, match=name):
        _ = KubernetesConfig.from_settings()


# ==================== RBAC ====================

RBAC = Path(__file__).parents[2] / "deploy" / "k8s" / "rbac.yaml"
# The API's verbs for each call of the backend, by (action, kind): the resource and the verb it needs.
NEEDED = {
    "create": ("create", ""),
    "read": ("get", ""),
    "find": ("list", ""),
    "patch": ("patch", ""),
    "delete": ("delete", ""),
}
KINDS = {
    "job": ("batch", "jobs"),
    "pod": ("", "pods"),
    "secret": ("", "secrets"),
    "networkpolicy": ("networking.k8s.io", "networkpolicies"),
}


def test_the_shipped_role_grants_every_call_the_backend_makes_and_nothing_it_does_not(
    tmp_path: Path, backend: KubernetesBackend, kube: FakeKube, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    granted: set[tuple[str, str, str]] = set()
    for document in yaml.safe_load_all(RBAC.read_text()):
        if document["kind"] == "Role":
            for rule in document["rules"]:
                granted |= {(g, r, v) for g in rule["apiGroups"] for r in rule["resources"] for v in rule["verbs"]}

    kube.task = terminated(0)
    kube.volumes["/results"] = {"result.json": GRADE}
    handle = backend.start(make_spec(tmp_path))
    _ = backend.wait(handle)
    backend.collect_results(handle, run_dir)
    _ = list(backend.logs(handle))
    _ = backend.list_runs()
    backend.cleanup(handle)
    kube.task = running()
    other = backend.start(make_spec(tmp_path, run_id="other"))
    backend.stop(other, grace=1)
    kube.pod_phase = "Succeeded"
    monkeypatch.setattr(kube, "pod_log", lambda pod, container, **kw: iter([]))
    backend.copy_from_image(IMAGE, PurePosixPath("/x"), tmp_path / "x")
    gone = backend.start(make_spec(tmp_path, run_id="gone"))
    del kube.objects[("pod", f"{gone.name}-abcde")]
    kube.job_conditions = [{"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}]
    with pytest.raises(BackendError):
        _ = backend.wait(gone)

    needed: set[tuple[str, str, str]] = set()
    for action, kind in kube.used:
        group, resource = KINDS.get(kind, ("", "pods"))
        if action == "log":
            needed.add(("", "pods/log", "get"))
        elif action == "exec":
            needed.add(("", "pods/exec", "create"))
        else:
            needed.add((group, resource, NEEDED[action][0]))
    assert needed <= granted
    # kubectl, not the client, forwards ports; `get` is for clusters that authorize a WebSocket stream that way.
    assert granted - needed == {
        ("", "pods/exec", "get"),
        ("", "pods/portforward", "create"),
        ("", "pods/portforward", "get"),
    }
