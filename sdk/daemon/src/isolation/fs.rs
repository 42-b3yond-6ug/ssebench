use std::ffi::{CStr, CString, OsStr, OsString};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt, lchown};
use std::path::Path;

/// Owner to give copied files, as (uid, gid).
pub type Owner = (u32, u32);

/// Copy the directory tree at `src` to `dst`, which must not exist.
///
/// `src` may be a tree the agent controls and changes while it is copied, so
/// it is walked through directory file descriptors and never follows a
/// symbolic link: links are copied as links, and an entry swapped for a link
/// mid-copy is skipped. FIFOs, sockets and device nodes are not copied.
/// Set-user-ID, set-group-ID and sticky bits are dropped, and the owner gets
/// read and write access to everything, as root had before. With `owner`,
/// every copied entry is given to that user; `dst` itself last, so the copy
/// is complete before the owner can enter it.
pub fn copy_tree(src: &Path, dst: &Path, owner: Option<Owner>) -> io::Result<()> {
    let root = open_dir(libc::AT_FDCWD, &cstring(src.as_os_str())?)?;
    let mode = fstat(root.as_raw_fd())?.st_mode;
    fs::create_dir(dst)?;
    fs::set_permissions(dst, fs::Permissions::from_mode(0o700))?;
    copy_contents(&root, dst, owner)?;
    finish(dst, dir_mode(mode), owner)
}

/// Copy one regular file, following no link, and give it `mode` and `owner`.
pub fn copy_file(src: &Path, dst: &Path, mode: u32, owner: Option<Owner>) -> io::Result<()> {
    let fd = open_file(libc::AT_FDCWD, &cstring(src.as_os_str())?)?;
    let mut input = File::from(fd);
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(dst)?;
    io::copy(&mut input, &mut output)?;
    finish(dst, mode, owner)
}

/// Remove a tree if it exists.
pub fn remove_tree(path: &Path) -> io::Result<()> {
    match fs::remove_dir_all(path) {
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        other => other,
    }
}

fn copy_contents(dir: &OwnedFd, dst: &Path, owner: Option<Owner>) -> io::Result<()> {
    for name in list(dir)? {
        let cname = cstring(&name)?;
        let st = match fstatat(dir.as_raw_fd(), &cname) {
            Ok(st) => st,
            Err(e) if vanished(&e) => continue,
            Err(e) => return Err(e),
        };
        let target = dst.join(&name);
        match st.st_mode & libc::S_IFMT {
            libc::S_IFDIR => {
                let sub = match open_dir(dir.as_raw_fd(), &cname) {
                    Ok(fd) => fd,
                    Err(e) if vanished(&e) => continue,
                    Err(e) => return Err(e),
                };
                let mode = fstat(sub.as_raw_fd())?.st_mode;
                fs::create_dir(&target)?;
                fs::set_permissions(&target, fs::Permissions::from_mode(0o700))?;
                copy_contents(&sub, &target, owner)?;
                finish(&target, dir_mode(mode), owner)?;
            }
            libc::S_IFREG => {
                let fd = match open_file(dir.as_raw_fd(), &cname) {
                    Ok(fd) => fd,
                    Err(e) if vanished(&e) => continue,
                    Err(e) => return Err(e),
                };
                let mode = fstat(fd.as_raw_fd())?.st_mode;
                let mut input = File::from(fd);
                let mut output = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .mode(0o600)
                    .open(&target)?;
                io::copy(&mut input, &mut output)?;
                finish(&target, file_mode(mode), owner)?;
            }
            libc::S_IFLNK => {
                let link = match readlinkat(dir.as_raw_fd(), &cname) {
                    Ok(link) => link,
                    Err(e) if vanished(&e) => continue,
                    Err(e) => return Err(e),
                };
                std::os::unix::fs::symlink(link, &target)?;
                if let Some((uid, gid)) = owner {
                    lchown(&target, Some(uid), Some(gid))?;
                }
            }
            _ => {}
        }
    }
    Ok(())
}

fn dir_mode(mode: libc::mode_t) -> u32 {
    (mode & 0o777) | 0o700
}

fn file_mode(mode: libc::mode_t) -> u32 {
    (mode & 0o777) | 0o600
}

fn finish(path: &Path, mode: u32, owner: Option<Owner>) -> io::Result<()> {
    if let Some((uid, gid)) = owner {
        lchown(path, Some(uid), Some(gid))?;
    }
    // After chown, which clears set-id bits, so the mode is exactly `mode`.
    fs::set_permissions(path, fs::Permissions::from_mode(mode))
}

/// An entry that was removed, or replaced by something else, while the tree
/// was being copied.
fn vanished(e: &io::Error) -> bool {
    matches!(
        e.raw_os_error(),
        Some(libc::ENOENT | libc::ELOOP | libc::ENOTDIR | libc::ENXIO | libc::EINVAL)
    ) || e.kind() == io::ErrorKind::InvalidData
}

fn cstring(s: &OsStr) -> io::Result<CString> {
    CString::new(s.as_bytes()).map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))
}

fn check(fd: libc::c_int) -> io::Result<OwnedFd> {
    if fd < 0 {
        Err(io::Error::last_os_error())
    } else {
        // SAFETY: fd is a descriptor that openat just returned to us.
        Ok(unsafe { OwnedFd::from_raw_fd(fd) })
    }
}

fn open_dir(dirfd: RawFd, name: &CStr) -> io::Result<OwnedFd> {
    let flags = libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC;
    // SAFETY: name is a valid NUL-terminated string.
    check(unsafe { libc::openat(dirfd, name.as_ptr(), flags) })
}

/// Open a regular file. O_NONBLOCK keeps a FIFO swapped in from blocking the
/// open; the type is checked on the descriptor.
fn open_file(dirfd: RawFd, name: &CStr) -> io::Result<OwnedFd> {
    let flags = libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK;
    // SAFETY: name is a valid NUL-terminated string.
    let fd = check(unsafe { libc::openat(dirfd, name.as_ptr(), flags) })?;
    if fstat(fd.as_raw_fd())?.st_mode & libc::S_IFMT != libc::S_IFREG {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "not a regular file",
        ));
    }
    Ok(fd)
}

fn fstat(fd: RawFd) -> io::Result<libc::stat> {
    // SAFETY: an all-zero stat is a valid value, and fstat only writes to it.
    let mut st: libc::stat = unsafe { std::mem::zeroed() };
    // SAFETY: st is a valid, writable stat.
    if unsafe { libc::fstat(fd, &mut st) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(st)
}

fn fstatat(dirfd: RawFd, name: &CStr) -> io::Result<libc::stat> {
    // SAFETY: as in fstat.
    let mut st: libc::stat = unsafe { std::mem::zeroed() };
    // SAFETY: name is NUL-terminated and st is writable.
    if unsafe { libc::fstatat(dirfd, name.as_ptr(), &mut st, libc::AT_SYMLINK_NOFOLLOW) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(st)
}

fn readlinkat(dirfd: RawFd, name: &CStr) -> io::Result<OsString> {
    let mut buf = vec![0u8; libc::PATH_MAX as usize];
    // SAFETY: buf is writable for buf.len() bytes.
    let n = unsafe {
        libc::readlinkat(
            dirfd,
            name.as_ptr(),
            buf.as_mut_ptr().cast::<libc::c_char>(),
            buf.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    buf.truncate(n as usize);
    Ok(OsString::from_vec(buf))
}

/// The names in a directory. Listing it through /proc/self/fd reads the
/// directory the descriptor holds, even if its path has been swapped since.
fn list(dir: &OwnedFd) -> io::Result<Vec<OsString>> {
    fs::read_dir(format!("/proc/self/fd/{}", dir.as_raw_fd()))?
        .map(|entry| entry.map(|e| e.file_name()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::MetadataExt;

    fn mode(path: &Path) -> u32 {
        fs::symlink_metadata(path).unwrap().mode() & 0o7777
    }

    #[test]
    fn copies_files_directories_and_links_without_following_links() {
        let tmp = tempfile::tempdir().unwrap();
        let secret = tmp.path().join("secret.txt");
        fs::write(&secret, "the answer").unwrap();

        let src = tmp.path().join("src");
        fs::create_dir_all(src.join("a/b")).unwrap();
        fs::write(src.join("a/b/file.txt"), "hello").unwrap();
        std::os::unix::fs::symlink(&secret, src.join("leak.txt")).unwrap();
        std::os::unix::fs::symlink(tmp.path(), src.join("up")).unwrap();

        let dst = tmp.path().join("dst");
        copy_tree(&src, &dst, None).unwrap();

        assert_eq!(
            fs::read_to_string(dst.join("a/b/file.txt")).unwrap(),
            "hello"
        );
        for link in ["leak.txt", "up"] {
            let meta = fs::symlink_metadata(dst.join(link)).unwrap();
            assert!(
                meta.file_type().is_symlink(),
                "{link} was not kept as a link"
            );
        }
        assert_eq!(fs::read_link(dst.join("leak.txt")).unwrap(), secret);
        // Nothing under the linked directory was copied.
        assert!(!dst.join("up").join("secret.txt").is_file() || dst.join("up").is_symlink());
    }

    #[test]
    fn a_source_that_is_a_link_is_refused() {
        let tmp = tempfile::tempdir().unwrap();
        fs::create_dir(tmp.path().join("real")).unwrap();
        std::os::unix::fs::symlink(tmp.path().join("real"), tmp.path().join("link")).unwrap();
        assert!(copy_tree(&tmp.path().join("link"), &tmp.path().join("dst"), None).is_err());
    }

    #[test]
    fn skips_fifos_and_drops_set_id_bits() {
        let tmp = tempfile::tempdir().unwrap();
        let src = tmp.path().join("src");
        fs::create_dir(&src).unwrap();
        let fifo = cstring(src.join("pipe").as_os_str()).unwrap();
        // SAFETY: fifo is a valid path string.
        assert_eq!(unsafe { libc::mkfifo(fifo.as_ptr(), 0o644) }, 0);
        fs::write(src.join("tool"), "#!/bin/sh\n").unwrap();
        fs::set_permissions(src.join("tool"), fs::Permissions::from_mode(0o4755)).unwrap();
        fs::write(src.join("ro"), "x").unwrap();
        fs::set_permissions(src.join("ro"), fs::Permissions::from_mode(0o444)).unwrap();
        fs::create_dir(src.join("rodir")).unwrap();
        fs::set_permissions(src.join("rodir"), fs::Permissions::from_mode(0o1555)).unwrap();

        let dst = tmp.path().join("dst");
        copy_tree(&src, &dst, None).unwrap();

        assert!(fs::symlink_metadata(dst.join("pipe")).is_err());
        assert_eq!(mode(&dst.join("tool")), 0o755);
        assert_eq!(mode(&dst.join("ro")), 0o644);
        assert_eq!(mode(&dst.join("rodir")), 0o755);
        fs::set_permissions(src.join("rodir"), fs::Permissions::from_mode(0o755)).unwrap();
    }

    #[test]
    fn gives_the_copy_to_the_owner() {
        // Without root, the only owner that chown accepts is ourselves.
        let tmp = tempfile::tempdir().unwrap();
        let src = tmp.path().join("src");
        fs::create_dir_all(src.join("d")).unwrap();
        fs::write(src.join("d/f"), "x").unwrap();
        let me = fs::metadata(tmp.path()).unwrap();
        let owner = (me.uid(), me.gid());

        let dst = tmp.path().join("dst");
        copy_tree(&src, &dst, Some(owner)).unwrap();
        for path in [dst.clone(), dst.join("d"), dst.join("d/f")] {
            let meta = fs::symlink_metadata(&path).unwrap();
            assert_eq!((meta.uid(), meta.gid()), owner);
        }
    }

    #[test]
    fn copy_file_sets_the_mode_and_refuses_links() {
        let tmp = tempfile::tempdir().unwrap();
        let src = tmp.path().join("run.sh");
        fs::write(&src, "#!/bin/sh\n").unwrap();
        let dst = tmp.path().join("copy.sh");
        copy_file(&src, &dst, 0o750, None).unwrap();
        assert_eq!(mode(&dst), 0o750);
        assert_eq!(fs::read_to_string(&dst).unwrap(), "#!/bin/sh\n");

        std::os::unix::fs::symlink(&src, tmp.path().join("link")).unwrap();
        assert!(
            copy_file(
                &tmp.path().join("link"),
                &tmp.path().join("c2"),
                0o600,
                None
            )
            .is_err()
        );
    }

    #[test]
    fn remove_tree_ignores_missing_paths() {
        let tmp = tempfile::tempdir().unwrap();
        remove_tree(&tmp.path().join("missing")).unwrap();
        fs::create_dir_all(tmp.path().join("x/y")).unwrap();
        remove_tree(&tmp.path().join("x")).unwrap();
        assert!(!tmp.path().join("x").exists());
    }
}
