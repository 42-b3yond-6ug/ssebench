package entrypoint

import (
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// agentUser is the unprivileged user the agent runs as.
const agentUser = "model"

// agentHome is the home of [agentUser] when the user database does not say.
const agentHome = "/home/model"

// account is a user's numeric identity.
type account struct {
	uid, gid uint32
	home     string
}

func lookupAccount(name string) (account, error) {
	u, err := user.Lookup(name)
	if err != nil {
		return account{}, err
	}
	uid, err := strconv.ParseUint(u.Uid, 10, 32)
	if err != nil {
		return account{}, err
	}
	gid, err := strconv.ParseUint(u.Gid, 10, 32)
	if err != nil {
		return account{}, err
	}
	return account{uid: uint32(uid), gid: uint32(gid), home: u.HomeDir}, nil
}

// agentEnvironment returns env with the identity of [agentUser]. `su -p` keeps the entrypoint's
// environment, whose HOME is root's /root, a directory the agent cannot read, so git, uv and the
// agents' own tools would fail on it. The home holds the git identity.
func agentEnvironment(env []string) []string {
	home := agentHome
	if a, err := lookupAccount(agentUser); err == nil && a.home != "" {
		home = a.home
	}
	// The last value of a repeated key is the one a child gets.
	return append(slices.Clone(env), "HOME="+home, "USER="+agentUser, "LOGNAME="+agentUser)
}

// credential runs a process as the account, without the supplementary groups
// of the process that starts it.
func (a account) credential() *syscall.Credential {
	return &syscall.Credential{Uid: a.uid, Gid: a.gid, Groups: []uint32{}}
}

// isRoot reports whether the entrypoint can change users. Tests run without
// root, and then every step that needs it is skipped.
var isRoot = func() bool { return os.Geteuid() == 0 }

// stopUserProcesses kills every process of the named user and waits until
// none is left. A helper started as that user runs kill(-1, SIGKILL), which
// signals all of the user's processes at once, so none can fork its way out;
// the process table is then checked and stragglers killed directly.
func stopUserProcesses(name string) error {
	if !isRoot() {
		return nil
	}
	a, err := lookupAccount(name)
	if err != nil {
		return err
	}
	if a.uid == 0 {
		return fmt.Errorf("refusing to kill every process of %s (uid 0)", name)
	}
	for round := 1; round <= 20; round++ {
		helper := exec.Command("/bin/bash", "-c", "kill -KILL -1")
		helper.SysProcAttr = &syscall.SysProcAttr{Credential: a.credential()}
		_ = helper.Run() // On Linux, kill(-1) does not signal the caller.

		left := processesOf(a.uid)
		if len(left) == 0 {
			return nil
		}
		for _, pid := range left {
			_ = syscall.Kill(pid, syscall.SIGKILL)
		}
		time.Sleep(time.Duration(round) * 10 * time.Millisecond)
	}
	if left := processesOf(a.uid); len(left) > 0 {
		return fmt.Errorf("processes of %s survived: %v", name, left)
	}
	return nil
}

// processesOf lists the live processes whose real, effective or saved uid is
// uid. Zombies no longer run, so they do not count.
func processesOf(uid uint32) []int {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil
	}
	var pids []int
	for _, e := range entries {
		pid, err := strconv.Atoi(e.Name())
		if err != nil || pid == os.Getpid() {
			continue
		}
		status, err := os.ReadFile(filepath.Join("/proc", e.Name(), "status"))
		if err != nil {
			continue
		}
		if statusMatches(string(status), uid) {
			pids = append(pids, pid)
		}
	}
	return pids
}

func statusMatches(status string, uid uint32) bool {
	want := strconv.FormatUint(uint64(uid), 10)
	matched, dead := false, false
	for _, line := range strings.Split(status, "\n") {
		if state, ok := strings.CutPrefix(line, "State:"); ok {
			state = strings.TrimSpace(state)
			dead = strings.HasPrefix(state, "Z") || strings.HasPrefix(state, "X")
		} else if ids, ok := strings.CutPrefix(line, "Uid:"); ok {
			fields := strings.Fields(ids)
			for i := 0; i < len(fields) && i < 3; i++ {
				matched = matched || fields[i] == want
			}
		}
	}
	return matched && !dead
}

// chownTree gives every entry under root to uid and gid, following no link.
// Only for trees that nobody else changes while it runs.
func chownTree(root string, uid, gid int) error {
	return filepath.WalkDir(root, func(path string, _ fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		return os.Lchown(path, uid, gid)
	})
}
