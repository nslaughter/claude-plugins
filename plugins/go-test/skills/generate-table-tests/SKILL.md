---
name: generate-table-tests
description: Generate table-driven test skeletons with subtests and edge cases inferred from function signatures. Use when the user asks to generate unit tests, table tests, or test scaffolding for a Go function.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate Table-Driven Tests

Generate a table-driven test skeleton with subtests for a Go function. Infers edge cases from parameter types and produces a ready-to-fill test file.

## Step 1 -- Identify the Target Function

Follow the [target identification procedure](../_common/references/target-identification.md) with:
- **skill-purpose**: table tests
- **candidate-guidance**: all exported functions

## Step 2 -- Evaluate Whether Table Tests Are the Right Approach

Read the code under test and evaluate whether table-driven tests are the best fit. See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference.

### BAD candidates for table tests -- recommend alternatives instead

| Subject | Why Table Tests Are Wrong | Recommend Instead |
|---|---|---|
| Encode/decode pairs with clear round-trip invariant | Table tests check specific examples. Property tests verify the invariant holds for *all* inputs, catching edge cases you'd never think to list. | **Property tests** -- offer `/generate-property-tests` |
| Parse/validate with untrusted input | Hand-picked table entries miss the weird inputs that crash parsers. Fuzz testing explores the input space automatically. | **Fuzz targets** -- offer `/generate-fuzz-target` |
| CLI tools / file-based workflows | Table tests can't express multi-step file I/O sequences cleanly. txtar scripts declare files, run commands, and check output in a single readable artifact. | **txtar script tests** -- offer `/generate-txtar-tests` |
| Performance comparison (before/after) | Table tests verify correctness, not speed. Benchmarks give ns/op, allocs, and support benchstat comparison. | **Benchmarks** -- offer `/generate-benchmark` |

**Tie-breaking rule**: if a function matches more than one BAD row, apply the first matching row in this priority order:
1. If the primary input is `[]byte`, `string`, or `io.Reader` and the function parses or decodes it from an external source → **Parse/validate with untrusted input** row (fuzz targets).
2. If the function forms one half of an Encode/Decode round-trip and neither input is raw untrusted bytes → **Encode/decode pairs** row (property tests).
3. Otherwise use the first row that matches.

If the subject matches a BAD row above, **stop immediately and do not proceed to Step 3**. Do not generate any test file. Redirect the user:

> "Table tests verify specific input/output pairs. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

Only continue to Step 3 if the user explicitly chooses "Proceed with table tests". If borderline, use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with table tests" as the second option.

## Step 3 -- Analyze the Function Signature

Read the file containing the target function. Extract:

1. **Function name** and whether it is a method (has a receiver).
2. **Receiver type** (if method): pointer vs value receiver, type name.
3. **Input parameters**: name, type, and whether the type is a pointer, slice, map, interface, or primitive.
4. **Return values**: types and count, noting which return is an `error`.
5. **Package name** from the file header.
6. **Imports** that the test file will need.

Also read the function body to understand:
- What error conditions it checks (nil checks, length checks, range validations).
- What branches exist (if/else, switch cases).
- What other functions or methods it calls.

## Step 4 -- Infer Edge Cases

Based on the parameter types, generate edge case entries for the test table. Apply these rules:

| Parameter Type | Edge Cases to Include |
|---|---|
| `string` | `""` (empty), a normal value, a string with unicode characters (`"\u00e9\u00e0\u00fc"`), a very long string (note in comment) |
| `int`, `int64`, etc. | `0`, `-1`, `math.MaxInt64`, `math.MinInt64` (adjust for bit width) |
| `uint`, `uint64`, etc. | `0`, `1`, `math.MaxUint64` (adjust for bit width) |
| `float64`, `float32` | `0.0`, `-1.0`, `math.MaxFloat64`, `math.NaN()`, `math.Inf(1)` |
| `bool` | `true`, `false` |
| `*T` (any pointer) | `nil`, a valid pointer to a zero-value `T`, a valid pointer to a populated `T` |
| `[]T` (any slice) | `nil`, `[]T{}` (empty), `[]T{oneElement}`, `[]T{multipleElements}` |
| `map[K]V` | `nil`, empty map `map[K]V{}`, single-entry map, map with multiple entries |
| `io.Reader` / `io.Writer` | `nil`, `bytes.NewReader(nil)`, `bytes.NewReader(validData)`, an erroring reader (note in comment) |
| `context.Context` | `context.Background()`, `context.TODO()`, a canceled context (note in comment) |
| `error` | `nil`, `errors.New("test error")` |
| `interface{}` / `any` | `nil`, a string, an int, a struct (note: add domain-specific types) |

For method receivers:
- If pointer receiver `*T`: always add a nil-receiver comment or TODO to the generated test file explaining why a nil `*T` cannot be safely tested as a standard table entry (e.g., it panics on method dispatch). If the type has an explicit nil guard that returns an error, add a separate subtest outside the table that calls the method on a typed nil and asserts the error.
- Generate a helper or use the constructor (e.g., `NewT(...)`) to create valid receiver instances -- never use raw struct literals.

## Step 5 -- Generate the Test File

Generate the test file in the same package as the target function. Name it following Go conventions: **always derive the test file name from the source file name, not the function or method name**. If the source file is `parser.go`, the test file is `parser_test.go` — even if testing a method named `Parse`, `Set`, or anything else. If `parser_test.go` already exists, generate the test function to be appended or placed in a new file named `parser_tabletest_test.go`.

Use this template structure:

```go
package <pkgname>

import (
    "testing"
    // additional imports as needed
)

func Test<FunctionName>(t *testing.T) {
    t.Parallel()

    tests := []struct {
        name    string
        // one field per input parameter
        // one field per return value for expected results
        wantErr bool
    }{
        {
            name: "zero value inputs",
            // zero values for all params
        },
        {
            name: "valid input",
            // reasonable valid values
        },
        // edge cases from Step 3
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            got, err := <FunctionName>(tt.<params>...)
            if (err != nil) != tt.wantErr {
                t.Errorf("<FunctionName>() error = %v, wantErr %v", err, tt.wantErr)
                return
            }
            if !tt.wantErr {
                // TODO: Add assertions for expected return values
                _ = got
            }
        })
    }
}
```

Every test function and subtest includes `t.Parallel()` by default. Check the project's `go.mod` version: if earlier than Go 1.22, add `tt := tt` before `t.Run` to capture the loop variable. See [parallelism convention](../_common/references/parallelism-convention.md) for exceptions where `t.Parallel()` should be omitted (e.g., tests using `t.Setenv`, shared mutable state, or `os.Chdir`).

Adapt the template based on what was learned in Step 2:

- If the function is a method, construct the receiver in each test case or in a setup helper.
- If the function returns multiple values, add fields for each expected return.
- If the function takes a `context.Context`, do **not** add `ctx` as a field in the test table struct. Pass `context.Background()` directly at the call site inside each table-driven subtest, and add a separate named subtest outside the table for the cancelled-context case.

  Wrong (do not do this):
  ```go
  tests := []struct {
      name string
      ctx  context.Context // WRONG — ctx must not be a table field
      key  string
  }{...}
  ```

  Correct:
  ```go
  tests := []struct {
      name string
      key  string // no ctx field
  }{...}
  for _, tt := range tests {
      t.Run(tt.name, func(t *testing.T) {
          t.Parallel()
          err := obj.Method(context.Background(), tt.key)
          ...
      })
  }
  t.Run("cancelled context", func(t *testing.T) {
      t.Parallel()
      ctx, cancel := context.WithCancel(context.Background())
      cancel()
      err := obj.Method(ctx, "key")
      if err == nil { t.Error("want error for cancelled context") }
  })
  ```
- If the function takes a `testing.T` or `testing.B`, it is itself a test helper -- do not wrap it.

## Step 6 -- Write the File

Write the generated test file using the Write tool. Before writing:

1. Check if the target test file already exists. If it does, check whether a function with the same test name already exists in it.
2. If the test function name conflicts, append a numeric suffix (e.g., `TestParseConfig2`).
3. If the file exists but has no conflict, use the Edit tool to append the new test function at the end of the file (before the final closing, if any).
4. If the file does not exist, write a new file.

Run `gofmt` on the generated file to ensure proper formatting:

```bash
gofmt -w <test_file_path>
```

## Step 7 -- Verify Compilation

Run the test with `-run` to verify the generated code compiles:

```bash
cd <package_directory> && go test -run "Test<FunctionName>" -count=1 -v ./... 2>&1 | head -30
```

If compilation fails, read the error output, fix the issue in the generated file, and re-run.

## Step 8 -- Present Results

Report to the user:

1. The path to the generated test file.
2. The number of test cases generated and a summary of edge cases included.
3. A list of `TODO` comments in the generated code that the user needs to fill in (expected values, domain-specific test cases).
4. Any compilation issues that were encountered and fixed.

Remind the user: "The generated test cases cover type-based edge cases. You should add domain-specific test cases that exercise your function's business logic, boundary conditions, and error scenarios specific to your application."
