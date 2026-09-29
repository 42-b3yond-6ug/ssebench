use crate::util::run_script;

#[test]
fn test_run_script_success() {
    let result = run_script("echo", &["hello".to_string(), "world".to_string()], ".");
    assert!(result.is_ok());
    let script_result = result.unwrap();
    assert_eq!(script_result.code, 0);
    assert!(script_result.stdout.contains("hello world"));
    assert!(script_result.success());
}

#[test]
fn test_run_script_failure() {
    let result = run_script("false", &[], ".");
    assert!(result.is_ok());
    let script_result = result.unwrap();
    assert_eq!(script_result.code, 1);
    assert!(!script_result.success());
}

#[test]
fn test_run_script_nonexistent() {
    let result = run_script("nonexistent_command_12345", &[], ".");
    assert!(result.is_err());
    // Error message is from std::io::Error - "No such file or directory"
    let error = result.unwrap_err();
    assert!(
        error.to_string().to_lowercase().contains("not found")
            || error.to_string().to_lowercase().contains("no such file")
    );
}

mod bencher {
    use std::fs;
    use std::sync::Arc;

    use crate::bench::BenchCore;
    use crate::isolation::TaskRunner;
    use crate::tools::Bencher;

    /// A task whose run script prints where it runs and what it was given.
    fn bencher() -> (tempfile::TempDir, Bencher) {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("task");
        let source = dir.path().join("src");
        for sub in ["scripts", "pocs/data", "diffs"] {
            fs::create_dir_all(root.join(sub)).unwrap();
        }
        fs::create_dir_all(&source).unwrap();
        fs::write(source.join("main.c"), "int main(void) { return 0; }\n").unwrap();
        fs::write(
            root.join("scripts/build.sh"),
            "#!/bin/sh\necho built > out\n",
        )
        .unwrap();
        fs::write(
            root.join("scripts/run.sh"),
            "#!/bin/sh\ncat out; cat \"$1\"; ls \"$(dirname \"$1\")\"\n",
        )
        .unwrap();
        for script in ["build.sh", "run.sh"] {
            let path = root.join("scripts").join(script);
            let mut perms = fs::metadata(&path).unwrap().permissions();
            std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
            fs::set_permissions(&path, perms).unwrap();
        }
        fs::write(root.join("pocs/data/poc.bin"), "crash me\n").unwrap();
        fs::write(root.join("pocs/data/helper.txt"), "helper\n").unwrap();
        fs::write(root.join("diffs/patch.diff"), "the answer\n").unwrap();
        fs::write(
            root.join("config.yaml"),
            format!(
                "id: t\nproject: p\nlanguage: c\nsource: {}\ntask_description: {{}}\n\
                 scripts:\n  build: scripts/build.sh\n  run: scripts/run.sh\n\
                 files:\n  patch: diffs/patch.diff\n  poc: [pocs/data/poc.bin]\n",
                source.display()
            ),
        )
        .unwrap();
        let bench = Arc::new(BenchCore::new(&root).unwrap());
        let runner = TaskRunner::unprivileged(&dir.path().join("scratch")).unwrap();
        (dir, Bencher::new(bench, runner))
    }

    #[test]
    fn a_poc_runs_in_the_build_with_its_directory_staged() {
        let (dir, mut bencher) = bencher();
        assert!(bencher.build(false).unwrap().success());
        let poc = dir.path().join("task/pocs/data/poc.bin");
        let out = bencher.run_poc(poc.to_str().unwrap()).unwrap();
        assert!(out.success(), "{out:?}");
        assert_eq!(out.stdout, "built\ncrash me\nhelper.txt\npoc.bin\n");
        // The relative spelling names the same PoC.
        assert!(bencher.run_poc("pocs/data/poc.bin").unwrap().success());
    }

    #[test]
    fn run_poc_refuses_anything_but_a_configured_poc() {
        let (dir, mut bencher) = bencher();
        assert!(bencher.build(false).unwrap().success());
        let answer = dir.path().join("task/diffs/patch.diff");
        for poc in [
            answer.to_str().unwrap(),
            "diffs/patch.diff",
            "pocs/../diffs/patch.diff",
        ] {
            let err = bencher.run_poc(poc).unwrap_err();
            assert!(err.to_string().contains("not a PoC"), "{poc}: {err}");
        }
    }

    #[test]
    fn grading_discards_the_agent_phase_build() {
        let (_dir, mut bencher) = bencher();
        assert!(bencher.build(false).unwrap().success());
        bencher.start_grading().unwrap();
        let out = bencher.run_poc("pocs/data/poc.bin").unwrap();
        assert_eq!(out.code, -1, "{out:?}");
    }
}
