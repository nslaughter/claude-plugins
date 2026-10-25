---
name: generate-fuzz-target
description: Generate Fuzz test functions targeting parsing, validation, and deserialization code with corpus seeds. Use when the user asks to fuzz-test a parser, validator, or deserializer in Go.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate Fuzz Target

Generate `Fuzz*` test functions for Go code that parses, validates, or deserializes input. Seeds the corpus from existing unit tests and configures type-aware fuzzing for the function's input parameters.

## Step 1 -- Identify the Target Function

Follow the [target identification procedure](../_common/references/target-identification.md) with:
- **skill-purpose**: fuzz targets
- **candidate-guidance**: functions that parse, validate, decode, unmarshal, or transform input

## Step 2 -- Evaluate Whether Fuzz Testing Is the Right Approach

Before evaluating, run this detection check:

**Encode/decode pair check** — search the same package for a function whose name is the inverse of the target:
- Encode ↔ Decode, Marshal ↔ Unmarshal, Pack ↔ Unpack, Compress ↔ Decompress, Serialize ↔ Deserialize, Encrypt ↔ Decrypt

```bash
grep -n "^func " <target_file> | grep -iE "(encode|decode|marshal|unmarshal|pack|unpack|compress|decompress|serialize|deserialize|encrypt|decrypt)"
```

If the target function's name matches one side of a pair AND a corresponding inverse exists in the package, **STOP immediately** — do not generate a fuzz test. Output the redirect message:

> "Fuzz tests explore the input space to find crashes and panics in parsers and validators. `<FunctionName>` is one half of an encode/decode pair — the key correctness property is `decode(encode(x)) == x`, which property tests verify across random inputs and fuzz tests do not. [/generate-property-tests](/generate-property-tests) is a better fit. Would you like to switch?"

Only proceed past this check if no inverse function exists in the package.

---

Read the code under test and evaluate whether fuzz testing is the best fit. See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference.

### BAD candidates for fuzz targets -- recommend alternatives instead

| Subject | Why Fuzz Is Wrong | Recommend Instead |
|---|---|---|
| Functions with round-trip invariants (encode/decode) | Fuzz testing finds crashes but doesn't verify *correctness* of output. Property tests verify invariants like `decode(encode(x)) == x` across random inputs. | **Property tests** -- offer `/generate-property-tests` |
| Functions taking only structured types (structs, configs) | Go's fuzzing engine only generates `[]byte`, `string`, `int`, `float`, `bool`. Complex structs need custom generation that `testing/quick` handles better. | **Property tests** -- offer `/generate-property-tests` |
| CLI tools / multi-step workflows | Fuzz generates raw values, not command-line invocations or file layouts. | **txtar script tests** -- offer `/generate-txtar-tests` |
| Pure functions with known edge cases | If you can enumerate the important inputs, table tests are more readable and run faster. Fuzz is for discovering *unknown* edge cases. | **Table tests** -- offer `/generate-table-tests` |
| Performance-sensitive code | Fuzz tests verify correctness, not speed. | **Benchmarks** -- offer `/generate-benchmark` |

If the subject matches a BAD row above, redirect the user using this pattern:

> "Fuzz tests explore the input space to find crashes and panics in parsers and validators. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

If borderline, use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with fuzz target" as the second.

## Step 3 -- Analyze the Function

Read the file containing the target function. Extract:

1. **Function signature**: parameters and return types.
2. **What the function does**: parsing, validation, deserialization, or transformation.
3. **Input types**: which parameters represent the fuzzable input (typically `[]byte`, `string`, `io.Reader`, or a struct that gets populated from raw input).
4. **Error behavior**: does it return an error? Does it panic on invalid input? (Panics are exactly what fuzz testing should find.)
5. **Package name** and required imports.

Determine the **fuzzing strategy** based on the input type:

| Input Type | Fuzzing Approach |
|---|---|
| `[]byte` | Direct `f.Add([]byte(...))` with byte slice seeds |
| `string` | Direct `f.Add("...")` with string seeds |
| `io.Reader` | Wrap fuzzed input in a reader. Two equivalent approaches — use whichever matches the existing test style in the package: `f.Add([]byte{...})` with `bytes.NewReader(data)`, or `f.Add("...")` with `strings.NewReader(data)` |
| Struct with fields | Use `f.Add()` with individual field values, reconstruct struct in fuzz function |
| Multiple params | Add each fuzzable param as a separate `f.Add()` argument |
| `int`, `float64`, etc. | Direct `f.Add(value)` with numeric seeds |

## Step 4 -- Harvest Seed Values from Existing Tests

Search for existing unit tests that call the target function:

Use Grep to search for references to the target function name in `*_test.go` files.

Read the matching test files and extract:

1. **Literal values** passed to the function in test cases (string literals, byte slices, numeric constants).
2. **Test fixture files** referenced by tests (look for `os.ReadFile`, `testdata/`, `embed` directives).
3. **Table-driven test inputs** from `tests := []struct{...}` patterns.

Collect these as seed values for the fuzz corpus. If no existing tests are found, generate reasonable seed values based on the function's purpose:

- For JSON parsers: `{}`, `[]`, `{"key":"value"}`, malformed JSON.
- For URL parsers: `https://example.com`, empty string, `://invalid`.
- For config parsers: a minimal valid config, an empty config.
- For validators: a valid input, an empty input, an input at boundary limits.

## Step 5 -- Generate the Fuzz Function

Generate the fuzz test in the same package. Name the file `<source>_fuzz_test.go` (e.g., `parser_fuzz_test.go`). If the file already exists, append to it using the Edit tool.

Use this template structure:

```go
package <pkgname>

import (
    "testing"
    // additional imports
)

func Fuzz<FunctionName>(f *testing.F) {
    // Seed corpus with values from existing tests
    f.Add(<seed1>)
    f.Add(<seed2>)
    f.Add(<seed3>)
    // ... more seeds

    f.Fuzz(func(t *testing.T, <fuzzParams>) {
        // Call the target function with fuzzed input.
        // The fuzz test succeeds as long as the function does not panic.
        // If the function returns an error, that is expected behavior
        // for invalid input -- not a failure.
        result, err := <FunctionName>(<fuzzParams>)
        if err != nil {
            // Invalid input is expected; skip further checks.
            return
        }

        // TODO: Add invariant checks on valid results.
        // Examples:
        // - Round-trip: re-encode result and compare
        // - Idempotency: calling the function twice yields same result
        // - Bounds: result values are within expected ranges
        _ = result
    })
}
```

Adapt based on the function's characteristics:

- **Parse/decode functions**: add a round-trip check. If there is a corresponding `Marshal`/`Encode` function, encode the result and decode again, then compare.
- **Validation functions**: if the function returns `bool` or `error`, no invariant check is needed beyond "does not panic."
- **Transformation functions**: check that output satisfies postconditions (e.g., output length, output format).
- **Functions that should never panic**: wrap the call in a deferred recover and call `t.Fatal` if a panic occurs, to distinguish panics from expected errors.

If the function takes a `context.Context`, use `context.Background()`.

If the function is a method on a type, construct a valid receiver instance before the fuzz loop:

```go
f.Fuzz(func(t *testing.T, data []byte) {
    p := &Parser{/* valid defaults */}
    _, _ = p.Parse(data)
})
```

## Step 6 -- Write the File

Write the generated fuzz test file. Before writing:

1. Check if the target file already exists.
2. If it does and contains a `Fuzz<FunctionName>` function, warn the user and ask whether to overwrite or generate with a different name.
3. If it exists but has no conflict, append the new fuzz function.

Run `gofmt` on the generated file:

```bash
gofmt -w <test_file_path>
```

## Step 7 -- Verify and Run a Quick Check

Verify the fuzz test compiles and runs briefly:

```bash
cd <package_directory> && go test -run "^$" -fuzz "Fuzz<FunctionName>" -fuzztime=5s ./... 2>&1
```

If compilation fails, read the error, fix the generated code, and re-run.

If the fuzz test immediately finds a crash during the 5-second check, report the crash to the user -- this is valuable. Show the crashing input and the panic/failure message.

## Step 8 -- Present Results

Report to the user:

1. The path to the generated fuzz test file.
2. The number of seed corpus entries added and their sources (existing tests, generated defaults).
3. Whether the 5-second fuzz check passed or found issues.
4. `TODO` items the user should address (invariant checks, additional seeds).
5. How to run extended fuzzing:

```
go test -fuzz Fuzz<FunctionName> -fuzztime=30s ./path/to/package
```

Remind the user: "Fuzz tests are most effective when run for extended periods. Consider running `go test -fuzz Fuzz<FunctionName> -fuzztime=5m` to find deeper issues. Any crashing inputs will be saved to `testdata/fuzz/` and replayed as regression tests automatically."
