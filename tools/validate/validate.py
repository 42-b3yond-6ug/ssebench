from multiprocessing import Value
from re import I
import yaml
import tempfile
import subprocess
import shutil
from pathlib import Path

SSE_DIR = Path("/ssebench")

def build(config: dict, work_dir: Path) -> int:
    build_script = config.get("scripts", {}).get("build", "")
    if not build_script:
        raise ValueError("No build script in config")
    result = subprocess.run(
        [SSE_DIR / build_script],
        cwd=work_dir,
        timeout=3600,
        capture_output=True
    )
    if result.returncode:
        print(result.stdout.decode('utf-8', errors='ignore'))
        print(result.stderr.decode('utf-8', errors='ignore'))
    return result.returncode


def run_poc(config: dict, work_dir: Path, poc_file: str, num_runs: int = 10) -> list[int]:
    run_script = config.get("scripts", {}).get("run", "")
    if not run_script:
        raise ValueError("No run script in config")
    results = []
    for i in range(num_runs):
        result = subprocess.run(
            [SSE_DIR / run_script, SSE_DIR / poc_file],
            cwd=work_dir,
            timeout=3600,
            capture_output=True
        )
        results.append(result.returncode)
    return results


def reproduce(config: dict, work_dir: Path, is_patched: bool = False, num_poc_runs: int = 10) -> None:
    state = "post-patch" if is_patched else "pre-patch"

    print(f"[*] [{state}] Building project...")
    if build(config, work_dir):
        raise RuntimeError(f"Project failed to build ({state})")

    poc_files = config.get("files", {}).get("poc", [])
    if not poc_files:
        print(f"[!] [{state}] No PoC files specified in config — skipping PoC testing.")
        return

    print(f"[*] [{state}] Running {len(poc_files)} PoC(s) {num_poc_runs} times each...")
    for i, poc_file in enumerate(poc_files, start=1):
        print(f"    → [{state}] Running PoC {i}/{len(poc_files)}: {poc_file}")
        try:
            results = run_poc(config, work_dir, poc_file, num_poc_runs)
            # TODO: Checking returncode only here is not enough,
            # programs can return non-zero without crashing
            crash_count = sum(1 for r in results if r != 0)
            all_crashed = crash_count == num_poc_runs
            none_crashed = crash_count == 0
            
            if all_crashed and is_patched:
                print(f"        [!] [{state}] PoC {poc_file} crashed in all {num_poc_runs} runs (shouldn't crash).")
            elif none_crashed and not is_patched:
                print(f"        [!] [{state}] PoC {poc_file} didn't crash in any of {num_poc_runs} runs (should crash).")
            else:
                print(f"        ✓ [{state}] PoC {poc_file} crashed in {crash_count}/{num_poc_runs} runs.")
        except subprocess.TimeoutExpired:
            print(f"        [!] [{state}] PoC {poc_file} timed out during {state} run.")
        except Exception as e:
            print(f"        [!] Error running PoC {poc_file} during {state}: {e}")


def apply_patch(patch_file: Path, work_dir: Path) -> None:
    """Apply a patch file using git apply if .git exists, otherwise use patch."""
    use_git = (work_dir / ".git").exists()
    tool_name = "git apply" if use_git else "patch"
    print(f"[*] Applying patch using {tool_name}...")
    
    with open(patch_file, "rb") as patch_file_handle:
        if use_git:
            subprocess.run(
                ["git", "apply", "-p", "1"],
                stdin=patch_file_handle,
                cwd=work_dir,
                timeout=3600,
                check=True,
                capture_output=True
            )
        else:
            subprocess.run(
                ["patch", "--batch", "--no-backup-if-mismatch", "-p1"],
                stdin=patch_file_handle,
                cwd=work_dir,
                timeout=3600,
                check=True,
                capture_output=True
            )


def run_func_test(config: dict, work_dir: Path, apply_test_diff: bool = True) -> int:
    test_script = config.get("scripts", {}).get("test", "")
    if not test_script:
        print("[!] No test script defined in config — skipping functional test.")
        return 0

    test_diff = config.get("files", {}).get("future_test", "")
    if test_diff and apply_test_diff:
        try:
            apply_patch(SSE_DIR / test_diff, work_dir)
        except subprocess.CalledProcessError as e:
            print("[!] Failed to apply future test patch.")
            print(e.stderr.decode(errors="ignore"))
            return 1
        except subprocess.TimeoutExpired:
            print("[!] Timeout while applying future test patch.")
            return 1

    print(f"[*] Executing functional test script...")
    try:
        result = subprocess.run(
            [SSE_DIR / test_script],
            cwd=work_dir,
            timeout=3600,
            capture_output=True
        )
        if result.returncode:
            print(result.stdout.decode('utf-8', errors='ignore'))
            print(result.stderr.decode('utf-8', errors='ignore'))
        return result.returncode
    except subprocess.TimeoutExpired:
        print("[!] Functional test timed out.")
        return 1


def validate(num_poc_runs: int = 10) -> None:
    print("[*] Loading configuration...")
    with open(SSE_DIR / "config.yaml", "r") as file:
        config = yaml.safe_load(file)

    print("[*] Checking required config fields...")
    source_dir = Path(config.get("source", ""))
    if not source_dir:
        raise ValueError("No source directory in config")

    if not config.get("project", ""):
        raise ValueError("No project name in config")
    if not config.get("language", ""):
        raise ValueError("No project language in config")
    if not config.get("task_description", {}):
        raise ValueError("No task_description in config")

    issue = config.get("task_description", {}).get("issue", "")
    crash_reports = config.get("task_description", {}).get("crash_report", [])
    bug_description = config.get("task_description", {}).get("bug_description", "")
    if not (issue or crash_reports or bug_description):
        raise ValueError("At least 1 field in task description must contain value")

    print("[*] Starting pre-patch reproduction (expecting crashes)...")
    tmp_dir = Path(tempfile.mkdtemp(dir="/tmp"))
    shutil.copytree(source_dir, tmp_dir, dirs_exist_ok=True, symlinks=True)
    try:
        reproduce(config, tmp_dir, is_patched=False, num_poc_runs=num_poc_runs)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    patch_diff = config.get("files", {}).get("patch", "")
    if not patch_diff:
        raise ValueError("No patch file in config")
    apply_patch(SSE_DIR / patch_diff, source_dir)

    print("[*] Starting post-patch reproduction (expecting no crashes)...")
    tmp_dir = Path(tempfile.mkdtemp(dir="/tmp"))
    shutil.copytree(source_dir, tmp_dir, dirs_exist_ok=True, symlinks=True)
    try:
        reproduce(config, tmp_dir, is_patched=True, num_poc_runs=num_poc_runs)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Check if test script exists
    test_script = config.get("scripts", {}).get("test", "")
    if not test_script or not (SSE_DIR / test_script).exists():
        print("[!] Test script not found — skipping functional tests.")
    else:
        print("[*] Running functional test (before applying test.diff)...")
        tmp_dir = Path(tempfile.mkdtemp(dir="/tmp"))
        shutil.copytree(source_dir, tmp_dir, dirs_exist_ok=True, symlinks=True)
        try:
            test_result_before = run_func_test(config, tmp_dir, apply_test_diff=False)
            if test_result_before:
                print("[!] Functional test failed (before applying test.diff)")
            else:
                print("[*] Functional test passed (before applying test.diff)")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # Check if test.diff exists before running second test
        test_diff = config.get("files", {}).get("future_test", "")
        if not test_diff or not (SSE_DIR / test_diff).exists():
            print("[!] Test diff not found — skipping functional test (after applying test.diff).")
        else:
            print("[*] Running functional test (after applying test.diff)...")
            tmp_dir = Path(tempfile.mkdtemp(dir="/tmp"))
            shutil.copytree(source_dir, tmp_dir, dirs_exist_ok=True, symlinks=True)
            try:
                test_result_after = run_func_test(config, tmp_dir, apply_test_diff=True)
                if test_result_after:
                    print("[!] Functional test failed (after applying test.diff)")
                else:
                    print("[*] Functional test passed (after applying test.diff)")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    print("[***] Validation completed!")


if __name__ == "__main__":
    validate()
    