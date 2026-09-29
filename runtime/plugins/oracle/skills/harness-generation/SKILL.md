---
name: harness-generation
description: Generate a harness for fuzzing.
---

# Harness Generation

The first step to set up fuzzing is to get a good harness.

A harness is a small piece of code that:

- Accepts arbitrary input from the fuzzer
- Transforms/parses it into a format the target expects
- Invokes the target functionality
- Ensures execution is bounded and observable (crashes, special exits, etc.)

## Process

### 1. Understand the PoC

We launch the fuzzing test with a porpose: to understand if the bug in the code
is fully patched.

You are provided with the PoC. A PoC contains a build script, a run script,
and, optionally, a harness, with some program input files. Running PoC will
trigger the "oracle", which could be either a sanitizer, an assertion, or
simply a `if-else` block in the harness code, to exit the program in an error
state.

### 2. Make a decision

PoC can help you to understand the bug. But keep in mind: the harness used by
PoC is not always usable for fuzzing.

You need to make a decision here, for testing this special bug via fuzzing:

- Option A: Use the compiled program itself, if available, as fuzzing harness
- Option B: Use or modify the PoC harness as fuzzing harness
- Option C: Write a new fuzzing harness

#### Option A: Use the compiled program itself as fuzzing harness

Use this option when the program itself can be compiled into a runnable
program, and is fast enough to iterate. For example, if the input format is
easy to mutate, and the program runs very fast, and the bug is observable
through sanitizers, it's fine to use program itself as harness.

#### Option B: Use or modify the PoC harness as fuzzing harness

Use this option when the PoC harness can be used for fuzzing. If the PoC
harness expects an input, then it may be suitable for fuzzing.

If the PoC harness hard-codes an input, you need to think about it:
- Is the input easy to generate or mutate?
- Can we convert the PoC harness into a fuzzing harness?

If both answer is yes, then it's fine to modify the PoC harness into a fuzzing
harness.

#### Option C: Write a new fuzzing harness

In some case the PoC harness is not usable for fuzzing. Writing a new fuzzing
harness is acceptable. However, we are testing for the special bug, not the
entire program, so it is still important to analysis the PoC harness itself, to
understand the necessary functions that we need to invoke.

It's also worth noting: If the fuzzing target is a binary program, not a
library, then the harness you wrote cannot create an invalid program state. In
other words, the crash you find through the harness can be converted into an
input of the original program that also triggers the bug.

# Harness Generation Rules

You are generating a fuzzing harness for a target project. Your goal is to
expose real bugs through realistic execution paths while maximizing fuzzing
efficiency.

A harness is not just something that crashes.  It is a plausible witness of a
bug under a realistic or defensible usage model.

You may simplify execution, but you must not increase the target’s power to
reach states that real users, callers, or attackers could not reach.

## Cleaner Rule Set

Every harness must satisfy ALL of the following:

1. Behavioral Plausibility The harness should model a realistic or defensible
   usage of the target.

2. Semantic Preservation Simplifications are allowed only if they do not change
   bug-relevant semantics.

3. Reachability Fidelity The harness must not introduce:
    - impossible states
    - impossible data values
    - impossible call sequences

   unless those states are externally reachable (e.g., attacker-controlled
   malformed input).

4. Fuzzing Efficiency The harness should:
    - remove irrelevant overhead
    - avoid slow or unrelated logic
    - maximize iteration speed

5. Clear Bug Observability The harness should:
    - isolate the bug-triggering path
    - make crashes or incorrect behavior easy to detect

## Allowed Simplifications

You MAY:
- bypass logging, UI, network, sleeps, retries
- stub irrelevant parameters
- skip initialization unrelated to the bug
- directly call deeper functions IF their state is realistically reachable
- replace nondeterminism (time, randomness) with deterministic values

## Forbidden Actions

You MUST NOT:
- fabricate impossible object states
- violate invariants that real execution cannot violate
- assign values that cannot come from real inputs
- construct call chains that do not exist or are not plausible
- use internal/private APIs unless externally reachable
- manually corrupt memory or state to force a crash


# Target-Specific Rules

## Binary Targets

The harness must correspond to a feasible execution slice of the real program.

### Data Flow Constraint Inputs must be derivable from:
- CLI arguments
- files
- environment variables
- IPC / network
- program logic

Bad example: func(non_null_ptr = NULL);
If no real caller can pass NULL, this is invalid.

Good example: Provide bytes directly to a parser as if read from a file.

### Control Flow Constraint Only use call sequences that exist in the code base.

Bad example: Calling unrelated helper functions in arbitrary order.

Good example: Calling a deep function directly with a state equivalent to real
execution.

### Key Rule (Binary)

“Could the program itself get here?”

---

## Library Targets

The harness models an external user of the API.

### Control Flow Flexibility

You MAY create new call sequences if they are plausible.

Good example: create_image → check_image → compress_image

Bad example: alloc → free → free (purely artificial misuse)

### Public API Boundary

- Prefer public / documented APIs
- Internal APIs only if the same behavior is reachable via public usage

Bad example: Calling __internal_helper() when not externally reachable


### Key Rule (Library)

“Could a reasonable external user get here?”

---

# Valid vs Invalid Usage Model

You must decide which bug model applies:

## 1. Valid Usage Bugs

- Inputs follow intended API contracts
- Focus: logic bugs, hidden memory issues

## 2. Externally Reachable Misuse

Inputs may be malformed IF attacker/user can cause them

Allowed:
    - malformed file input
    - invalid serialized data

Not allowed:
    - forging impossible internal structures
    - violating invariants unreachable from API

---

# Examples

---

## Example 1: Impossible NULL

Invalid: func(non_null_ptr = NULL);

Valid only if:
- allocation failure can produce NULL
- parsing can omit the field

---

## Example 2: Artificial Double Free

Invalid sequence: p = my_alloc() my_free(p) my_free(p)

This is not realistic usage unless the API explicitly allows it.

---

## Example 3: Realistic Hidden Bug

Valid sequence: img = create_image(data) check_image(img) compress_image(img)

If this reveals a double free internally, it is a valid harness.

---

# Final Guideline

- Binary: respect real execution paths
- Library: respect plausible API usage
- Always: simplify execution, not semantics
