---
name: fuzzing
description: Run fuzzing tests.
---

# Fuzzing

After you picked (or generated) the harness, and collected the fuzzing seeds,
you should start a fuzzing test. The test should be run in the background for
at least 10 minutes. After that, you should inspect the results, including the
crashes, timeouts, and the fuzzing status (exec per seconds, coverage, etc.).

## Processes

### 1. Compile the project (and harness, if any)

AFL++ comes with a central compiler `afl-cc` that incorporates various different
kinds of compiler targets and instrumentation options.

You need to setup the compiling correctly. For example, if the harness requires
sanitizers to observe the buggy behavior, you need to correctly setup the
sanitzers during building.

The following sanitizers have built-in support in AFL++:

- ASAN = Address SANitizer, finds memory corruption vulnerabilities like
use-after-free, NULL pointer dereference, buffer overruns, etc. Enabled with
export AFL_USE_ASAN=1 before compiling.
- MSAN = Memory SANitizer, finds read accesses to uninitialized memory, e.g., a
local variable that is defined and read before it is even set. Enabled with
export AFL_USE_MSAN=1 before compiling.
- UBSAN = Undefined Behavior SANitizer, finds instances where - by the C and
C++ standards - undefined behavior happens, e.g., adding two signed integers
where the result is larger than what a signed integer can hold. Enabled with
export AFL_USE_UBSAN=1 before compiling.

### 2. Fuzzing (single core)

In this final step, fuzz the target.

a) Running afl-fuzz

- export AFL_SKIP_CPUFREQ=1 for afl-fuzz to skip unnecessary checks.
- set AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1, we can't modify the kernel.
- pass AFL_NO_AFFINITY=1 to afl-fuzz.
- If you have fuzzing seeds, then specify this directory with the -i option.

a) Collecting inputs:

afl-fuzz -i input -o output -- bin/target -someopt @@

Note that the directory specified with -o will be created if it does not exist.

It can be valuable to run afl-fuzz in a screen or tmux shell so you can log
off, or afl-fuzz is not aborted if you are running it in a remote ssh session
where the connection fails in between. Only do that though once you have
verified that your fuzzing setup works! Run it like screen -dmS afl-main --
afl-fuzz -M main-$HOSTNAME -i ... and it will start away in a screen session.
To enter this session, type screen -r afl-main. You see - it makes sense to
name the screen session same as the afl-fuzz -M/-S naming :-) For more
information on screen or tmux, check their documentation.

If you need to stop and re-start the fuzzing, use the same command line options
(or even change them by selecting a different power schedule or another
mutation mode!) and switch the input directory with a dash (-):

afl-fuzz -i - -o output -- bin/target -someopt @@

Adding a dictionary is helpful. You have the following options:

See the directory dictionaries/, if something is already included for your data
format, and tell afl-fuzz to load that dictionary by adding -x
dictionaries/FORMAT.dict. With afl-clang-lto, you have an autodictionary
generation for which you need to do nothing except to use afl-clang-lto as the
compiler. With afl-clang-fast, you can set
AFL_LLVM_DICT2FILE=/full/path/to/new/file.dic to automatically generate a
dictionary during target compilation. Adding AFL_LLVM_DICT2FILE_NO_MAIN=1 to
not parse main (usually command line parameter parsing) is often a good idea
too. You also have the option to generate a dictionary yourself during an
independent run of the target, see utils/libtokencap/README.md. Finally, you
can also write a dictionary file manually, of course.

afl-fuzz has a variety of options that help to workaround target quirks like
very specific locations for the input file (-f), performing deterministic
fuzzing (-D) and many more. Check out afl-fuzz -h.

By default, afl-fuzz never stops fuzzing. To terminate AFL++, press Control-C
or send a signal SIGINT. You can limit the number of executions or approximate
runtime in seconds with options also.
