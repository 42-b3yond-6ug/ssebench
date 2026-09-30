import 'just/config.just'
import 'just/setup.just'
import 'just/bench.just'
import 'just/dev.just'
import 'just/infra.just'
import 'just/dataset.just'
import 'just/verify.just'
import 'just/release.just'

# List the recipes by group
[private]
default:
    @just --list --unsorted
