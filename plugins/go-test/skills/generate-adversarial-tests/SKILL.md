---
name: generate-adversarial-tests
description: Generate tests that deliberately probe a function's assumptions, boundary conditions, and undocumented behaviors. Use when the user asks to stress-test, adversarially test, or probe the contract of a Go function.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate Adversarial Tests

Generate tests that deliberately probe a function's assumptions, boundary conditions, and undocumented behaviors. Each test case targets a specific contract element with a comment explaining what assumption it's trying to break.

## Step 1 -- Identify the Target Function

Follow the [target identification procedure](../_common/references/target-identification.md) with:
- **skill-purpose**: adversarial tests
- **candidate-guidance**: functions with preconditions, complex state requirements, concurrency exposure, or implicit contracts

## Step 2 -- Evaluate Whether Adversarial Tests Are the Right Approach

Read the code under test and evaluate whether adversarial testing is the best fit. See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference.

### GOOD candidates for adversarial tests

| Category | Why Adversarial Tests Fit |
|---|---|
| Functions with documented preconditions (godoc, comments, panic guards) | Deliberately violate each precondition and verify graceful failure |
| Functions with complex state requirements (initialized structs, open connections) | Test with partially initialized, nil-field, or zero-value receivers |
| Concurrency-exposed APIs | Test for races with concurrent calls, interleaved operations |
| Functions with implicit contracts (order-dependent calls, must-call-Close) | Violate the implicit ordering and verify behavior |
| Error-handling paths | Force every error return by constructing inputs that trigger each branch |
| Type assertions / interface casts | Pass unexpected concrete types behind interfaces |

### BAD candidates for adversarial tests -- recommend alternatives instead

| Subject | Why Adversarial Tests Are Wrong | Recommend Instead |
|---|---|---|
| Functions with no documented contract or preconditions | Nothing to test against without a contract -- need specification first. | Write documentation/godoc first, then return |
| Parse/validate untrusted input | Fuzz testing explores far more adversarial inputs automatically. | **Fuzz targets** -- offer `/generate-fuzz-target` |
| Pure functions with simple types (string->string, int->int) | Table tests with edge cases already cover boundary conditions for simple signatures. | **Table tests** -- offer `/generate-table-tests` |
| CLI tools / file-based workflows | txtar scripts test adversarial CLI scenarios more naturally. | **txtar script tests** -- offer `/generate-txtar-tests` |

If the subject matches a BAD row above, redirect the user using this pattern:

> "Adversarial tests deliberately violate a function's contract to probe assumptions and boundary conditions. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

If borderline, use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with adversarial tests" as the second.

## Step 3 -- Analyze the Function's Contract

Read the file containing the target function. Extract the function's contract by identifying:

1. **Documented preconditions**: godoc comments, inline comments describing expectations, `// must be called after ...`, `// requires non-nil ...`.
2. **Implicit preconditions**: nil checks, length checks, type assertions, map lookups in the function body that reveal what the function assumes about its inputs.
3. **Panic conditions**: explicit `panic()` calls, or operations that will panic on nil (dereferences, slice indexing, map writes to nil maps).
4. **Error return paths**: every `return ..., err` or `return ..., fmt.Errorf(...)` -- enumerate each distinct error condition.
5. **Receiver state requirements**: fields the method reads that must be initialized (e.g., a `*sql.DB` field, a mutex, a channel).
6. **Concurrency annotations**: comments like `// safe for concurrent use`, `// must not be called concurrently`, or the presence of mutexes/atomics.
7. **Implicit ordering contracts**: methods that must be called before or after this function (Init/Close, Open/Write, Start/Stop).

## Step 4 -- Design Adversarial Test Cases

For each contract element identified in Step 3, design a test case that deliberately violates it. Use these strategies:

| Strategy | What It Probes | Example |
|---|---|---|
| Nil injection | Nil pointer/slice/map/interface where non-nil expected | Pass nil for every pointer param, nil receiver |
| Zero-value assault | Zero-value struct/receiver when initialization required | `(&Server{}).Handle(req)` with no `Listen()` |
| Boundary overflow | Integer overflow, max-length strings, huge slices | `math.MaxInt64`, `strings.Repeat("a", 1<<20)` |
| Type confusion | Unexpected concrete types behind interfaces | Pass `*os.File` where simple `io.Reader` expected |
| Concurrency stress | Race conditions on shared state | Call method from 10 goroutines with `-race` |
| Error path forcing | Trigger every `return ..., err` | Construct inputs that hit each error branch |
| State violation | Use API out of documented order | Call `Write` before `Open`, `Next` before `Init` |
| Context abuse | Canceled/expired context, nil context | `context.WithCancel` + immediate cancel |

Design rules:
- Each test case gets a comment: `// Adversarial: [strategy] -- [what assumption this violates]`
- Focus on *intentional, reasoned* cases -- each one targets a specific assumption, unlike fuzz which explores randomly.
- Prioritize strategies that match the contract elements found in Step 3. Skip strategies that don't apply (e.g., skip "context abuse" if the function takes no context; skip "concurrency stress" if the function or type is documented as "not safe for concurrent use" or has no shared mutable state).

## Step 5 -- Generate the Test File

Generate the adversarial test in the same package. Name the file `<source>_adversarial_test.go` (e.g., `server_adversarial_test.go`). If the file already exists, append to it using the Edit tool.

Use subtests grouped by strategy:

```go
package <pkgname>

import (
    "testing"
    // additional imports as needed
)

func TestAdversarial<FunctionName>(t *testing.T) {
    t.Parallel()

    t.Run("nil_injection", func(t *testing.T) {
        t.Parallel()
        // Adversarial: nil injection -- <FunctionName> assumes non-nil <param>;
        // verify it returns an error (or panics gracefully) rather than
        // dereferencing nil.
        defer func() {
            if r := recover(); r != nil {
                t.Logf("panic on nil <param>: %v", r)
            }
        }()
        _, err := <FunctionName>(nil)
        if err == nil {
            t.Error("expected error for nil <param>, got nil")
        }
    })

    t.Run("zero_value", func(t *testing.T) {
        t.Parallel()
        // Adversarial: zero-value assault -- calling <MethodName> on a
        // zero-value receiver without initialization.
        var s <StructType>
        defer func() {
            if r := recover(); r != nil {
                t.Logf("panic on zero-value receiver: %v", r)
            }
        }()
        s.<MethodName>()
    })

    t.Run("boundary", func(t *testing.T) {
        t.Parallel()
        // Adversarial: boundary overflow -- <FunctionName> does not document
        // a maximum length; verify behavior at extreme sizes.
        huge := strings.Repeat("a", 1<<20)
        _, err := <FunctionName>(huge)
        if err != nil {
            t.Logf("error on huge input: %v", err)
        }
    })

    t.Run("concurrency", func(t *testing.T) {
        // No t.Parallel() -- concurrency stress subtests deliberately race
        // goroutines against each other; outer parallelism adds noise.
        // See: ../_common/references/parallelism-convention.md
        //
        // Adversarial: concurrency stress -- call <FunctionName> from
        // multiple goroutines to surface races. Run with -race.
        var wg sync.WaitGroup
        for i := 0; i < 10; i++ {
            wg.Add(1)
            go func() {
                defer wg.Done()
                <FunctionName>(validInput)
            }()
        }
        wg.Wait()
    })
}
```

The outer test function and most subtests include `t.Parallel()` by default. The exception is concurrency-stress subtests, which manage their own goroutines and should not have additional parallelism from the test framework. See [parallelism convention](../_common/references/parallelism-convention.md) for the full rule and exceptions.

Key difference from other test types: adversarial tests expect failure modes (panics, errors, graceful degradation), not correct outputs.

- Use `recover()` for tests that probe panic conditions. Log the panic value with `t.Logf` so the user can see what happened.
- Use error assertions for tests that probe error paths.
- Do NOT mark a controlled panic as a test failure -- the purpose is to discover whether the function panics, not to prevent it. A `t.Logf` recording the panic is the right signal.
- Mark a test as failed only when the function silently produces wrong results or corrupts state (e.g., writes to a nil map without error).

Adapt the template to only include strategy groups that apply to the target function. A function with no concurrency exposure should not get a `concurrency` subtest.

## Step 6 -- Write the File

Write the generated adversarial test file. Before writing:

1. Check if the target file already exists.
2. If it does and contains a `TestAdversarial<FunctionName>` function, warn the user and ask whether to overwrite or generate with a different name.
3. If it exists but has no conflict, append the new test function.

Run `gofmt` on the generated file:

```bash
gofmt -w <test_file_path>
```

## Step 7 -- Verify Compilation

Verify the adversarial tests compile and run:

```bash
cd <package_directory> && go test -run "TestAdversarial<FunctionName>" -v -count=1 ./... 2>&1
```

If compilation fails, read the error, fix the generated code, and re-run.

Suggest running with the race detector:

```bash
cd <package_directory> && go test -run "TestAdversarial<FunctionName>" -race -v -count=1 ./... 2>&1
```

## Step 8 -- Present Results

Report to the user:

1. The path to the generated adversarial test file.
2. The number of test cases grouped by strategy (e.g., "3 nil injection, 2 zero-value, 1 concurrency stress").
3. Which contract elements were probed and what assumptions each test targets.
4. Any panics or crashes discovered during the verification run in Step 7.
5. How to run with the race detector:

```
go test -run TestAdversarial<FunctionName> -race -v ./path/to/package
```

Remind the user: "Adversarial tests are designed to probe assumptions, not to pass. Review each test case: if a panic or unexpected error surfaces, decide whether the function needs hardening or the caller contract needs documenting. Tests that reveal undocumented panics are the most valuable findings."
