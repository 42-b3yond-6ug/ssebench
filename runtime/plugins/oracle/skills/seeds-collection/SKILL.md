---
name: seeds-collection
description: Collect useful corpus as fuzzing seeds. Use before launch fuzzing.
---

# Seeds Collection

Before launching fuzzing, use this skill to collect fuzzing seeds. Good fuzzing
seeds would increase coverage and save a lot of exploration time.

## Process

### 1. Locate the entrypoint

Depending on the project we want to fuzz, the fuzzing target could be either a
program (like a jpg format parser), or a harness (a small program calls some
library APIs).

Locate the entrypoint of fuzzing. The entrypoint can be either the `main`
function of the program, or the libFuzzing special entrypoint
`LLVMFuzzerTestOneInput`.

### 2. Understand the input format

Entrypoint usually expects a special input format. Correct understanding of
this format would greatly save us time spending on exploration to increase
coverage.

Input could be a common file format, like JPG pictures or PDF files. Or it
could be a special format required by the harness, for example it may have
byte layout requirement.

### 3. Analysis the PoC

You are provided with the PoC. A PoC contains a build script, a run script,
and, optionally, a harness, with some program input files. Running PoC will
trigger the "oracle", which could be either a sanitizer, an assertion, or
simply a `if-else` block in the harness code, to exit the program in an error
state.

PoC can further help you to understand the input format. But keep in mind: the
PoC harness is not always aligned with the harness we will use for fuzzing.

### 4. Generate some seeds

Once you understand the input, you can generate some initial fuzzing seeds. In
most cases, the seeds are not pure text, so you need to use bash or Python
scripts to generate such files. Notice the environment does not have Internet,
so you may not use third party dependencies as they can't be downloaded.

### 5. Making the input corpus unique

Use the AFL++ tool afl-cmin to remove inputs from the corpus that do not
produce a new path/coverage in the target:

Put all files from step a into one directory, e.g., INPUTS. Run afl-cmin:

If the target program is to be called by fuzzing as bin/target INPUTFILE,
replace the INPUTFILE argument that the target program would read from with @@:

afl-cmin -i INPUTS -o INPUTS_UNIQUE -- bin/target -someopt @@

If the target reads from stdin (standard input) instead, just omit the @@ as
this is the default:

afl-cmin -i INPUTS -o INPUTS_UNIQUE -- bin/target -someopt

This step is highly recommended, because afterwards the testcase corpus is not
bloated with duplicates anymore, which would slow down the fuzzing progress!
