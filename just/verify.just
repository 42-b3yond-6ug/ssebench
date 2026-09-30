# Run the heavy checks that pull requests skip in CI, here and in parallel: `just verify` for all, `just verify e2e kind` for some
[group('verify')]
verify *args:
    tools/verify/verify.sh "$@"

# Remove the images that `just verify` built in this checkout's registry prefix
[group('verify')]
verify-clean:
    tools/verify/verify.sh clean
