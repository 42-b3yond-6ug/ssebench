package entrypoint

import (
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"syscall"
	"testing"
)

func TestStatusMatchesRealEffectiveAndSavedUID(t *testing.T) {
	status := func(state, uids string) string {
		return "Name:\tbash\nState:\t" + state + "\nUid:\t" + uids + "\nGid:\t0\t0\t0\t0\n"
	}
	for _, tc := range []struct {
		status string
		want   bool
	}{
		{status("S (sleeping)", "1000\t1000\t1000\t1000"), true},
		{status("R (running)", "1000\t0\t0\t0"), true},
		{status("S (sleeping)", "0\t0\t1000\t0"), true},
		{status("S (sleeping)", "0\t0\t0\t1000"), false},
		{status("Z (zombie)", "1000\t1000\t1000\t1000"), false},
		{status("S (sleeping)", "10000\t10000\t10000\t10000"), false},
		{"Name:\tx\n", false},
	} {
		if got := statusMatches(tc.status, 1000); got != tc.want {
			t.Errorf("statusMatches(%q) = %v, want %v", tc.status, got, tc.want)
		}
	}
}

func TestProcessesOfListsChildren(t *testing.T) {
	child := exec.Command("sleep", "30")
	if err := child.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = child.Process.Kill(); _ = child.Wait() }()
	pids := processesOf(uint32(os.Getuid()))
	if !slices.Contains(pids, child.Process.Pid) || slices.Contains(pids, os.Getpid()) {
		t.Errorf("processesOf = %v, want the child %d and not ourselves", pids, child.Process.Pid)
	}
}

func TestStopUserProcessesNeedsRoot(t *testing.T) {
	saved := isRoot
	t.Cleanup(func() { isRoot = saved })
	isRoot = func() bool { return false }
	if err := stopUserProcesses("no-such-user"); err != nil {
		t.Errorf("without root: %v, want a no-op", err)
	}
	isRoot = func() bool { return true }
	if err := stopUserProcesses("no-such-user"); err == nil {
		t.Error("an unknown user was accepted")
	}
}

func TestReturnArchiveRestoresTheOwnerWithoutFollowingLinks(t *testing.T) {
	archive := t.TempDir()
	outside := filepath.Join(t.TempDir(), "outside")
	if err := os.WriteFile(outside, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(archive, "sub"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(archive, "sub", "link")); err != nil {
		t.Fatal(err)
	}
	rt := newRuntime(Config{ArchivePath: archive, ResultsPath: t.TempDir()}, []string{"true"})
	// Without root, chown only accepts our own ids.
	rt.archiveOwner = &[2]int{os.Getuid(), os.Getgid()}
	rt.returnArchive()
	for _, p := range []string{archive, filepath.Join(archive, "sub"), filepath.Join(archive, "sub", "link")} {
		info, err := os.Lstat(p)
		if err != nil {
			t.Fatal(err)
		}
		if st := info.Sys().(*syscall.Stat_t); int(st.Uid) != os.Getuid() {
			t.Errorf("%s owned by %d", p, st.Uid)
		}
	}
}

func TestSetupArchiveLeavesTheArchiveAloneWhenTheModeDoesNotWriteIt(t *testing.T) {
	archive := t.TempDir()
	results := filepath.Join(t.TempDir(), "results")
	cfg := Config{ArchivePath: archive, ResultsPath: results, AgentWritesArchive: false}
	rt := newRuntime(cfg, []string{"true"})
	if err := os.Chmod(archive, 0o700); err != nil {
		t.Fatal(err)
	}

	if err := rt.setupArchive(); err != nil {
		t.Fatal(err)
	}

	// The results directory is created and world-readable but not world-writable.
	info, err := os.Stat(results)
	if err != nil || info.Mode().Perm()&0o022 != 0 {
		t.Errorf("results mode = %v, %v; want no group/other write", info.Mode().Perm(), err)
	}
	// The archive is untouched: the mode said the agent does not write it.
	if info, err := os.Stat(archive); err != nil || info.Mode().Perm() != 0o700 {
		t.Errorf("archive mode = %v, %v; want it left at 0700", info.Mode().Perm(), err)
	}
	if rt.archiveOwner != nil {
		t.Error("archiveOwner recorded for a mode that does not write the archive")
	}
}
