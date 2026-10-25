---
name: generate-txtar-tests
description: Generate txtar-based script tests for CLI tools, file-processing commands, and multi-step workflows using testscript. Use when the user asks to test a CLI tool, command, or file-processing program with integration-style tests.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate txtar Script Tests

Generate txtar-based test scripts using `github.com/rogpeppe/go-internal/testscript` for Go code that involves CLI commands, file I/O, or multi-step workflows. Before generating, evaluate whether txtar is the right testing approach for the subject under test and redirect the user to a better alternative if not.

## Step 1 -- Identify the Subject Under Test

Check whether the user specified what they want to test.

- If the user provided a command name, binary, or main package path, locate it:

Use Grep to search for `func main()` in `*.go` files across the project.

- If the user provided a file path, read the file to understand what it does.
- If the user provided neither, ask: "What would you like to generate txtar tests for? Please provide the command name, main package path, or describe the functionality."

## Step 2 -- Evaluate Whether txtar Is the Right Approach

See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference of test types and code characteristics.

Read the code under test and classify it. txtar script tests are **specifically designed for** testing programs and workflows that interact with the filesystem and produce observable output. They are the wrong tool for many common Go testing scenarios.

### GOOD candidates for txtar tests

Generate txtar tests if the subject under test matches **any** of these:

| Category | Examples |
|---|---|
| CLI tools / commands | Programs with `func main()`, cobra/urfave commands, tools invoked via `os/exec` |
| File-processing programs | Tools that read input files, transform them, and write output files |
| Code generators | `go generate` tools, protobuf generators, template-based generators |
| Build/module tooling | Custom `go` tool wrappers, module proxies, dependency tools |
| Multi-file workflows | Operations that require a specific directory layout to function |
| Configuration loaders | Programs that read config files from disk and behave accordingly |
| Script-like operations | Install scripts, migration tools, setup utilities |

### BAD candidates for txtar tests -- recommend alternatives instead

If the subject under test matches any category below, **do not generate txtar tests**. Instead, inform the user why txtar is not appropriate and recommend the better alternative. Use this phrasing pattern:

> "txtar script tests verify CLI tools and file-based workflows via commands, stdout, and exit codes. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

Then offer to generate the recommended test type instead.

| Subject Under Test | Why txtar Is Wrong | Recommend Instead |
|---|---|---|
| Pure functions (no I/O, no side effects) | txtar adds process overhead and obscures assertion failures. Table-driven tests give direct, precise assertions on return values. | **Table-driven tests** -- offer to run `/generate-table-tests` |
| Library/package APIs | txtar tests run commands, not function calls. Calling library functions requires writing a throwaway main wrapper, which is brittle. | **Standard Go unit tests** with direct function calls |
| HTTP handlers / servers | txtar has no built-in HTTP support. You would need to shell out to `curl` and parse text output, losing type safety. | **`httptest.NewServer`** with `net/http/httptest` for handler tests, or table-driven tests for handler logic |
| Database / external service integration | txtar cannot manage database state, connections, or service lifecycle. | **Integration tests** with `TestMain` setup/teardown and `testing.Short()` guards |
| Performance-sensitive code | txtar tests spawn subprocesses, adding ~100ms overhead per test case minimum. No benchmark support. | **Benchmarks** -- offer to run `/generate-benchmark` |
| Input validation / parsing functions | Fuzz testing explores the input space far more effectively than hand-written txtar cases. | **Fuzz targets** -- offer to run `/generate-fuzz-target` |
| Code with complex mock requirements | txtar has no mocking infrastructure. You would need real binaries for every dependency. | **Standard tests with mocks** -- offer to run `/generate-mocks` |
| Concurrency / race-condition testing | txtar scripts execute sequentially. No support for `-race` flag on the code under test (only on the test binary). | **Standard tests** with `-race` flag and `sync` primitives |
| Snapshot / golden-file tests (of function output) | txtar can do golden files but `testscript` is overkill if you're just comparing function output strings. | **`txtar` package for golden files** (not full `testscript`) or simple `golden_test.go` with `testdata/` |

If the subject is borderline (e.g., a library that also has a CLI), use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with txtar tests" as the second.

## Step 3 -- Check for testscript Dependency

Verify the project has the testscript dependency:

Use Grep to search for `go-internal/testscript` in `go.mod` and `go.sum`.

If not present, note that the user will need to add it:

```bash
go get github.com/rogpeppe/go-internal/testscript@latest
```

Also check whether the project already has txtar tests to learn existing conventions:

Use Glob to find existing txtar test files: `**/*.txtar` and `**/testdata/script/*.txt`.

If existing txtar tests are found, read 1-2 of them to understand the project's conventions (naming, directory layout, custom commands, setup patterns).

## Step 4 -- Analyze the Command Interface

For the CLI tool or command being tested, determine:

1. **How it is invoked**: binary name, subcommands, flags.
2. **What input it reads**: stdin, files, environment variables, config files.
3. **What output it produces**: stdout, stderr, exit codes, output files.
4. **What side effects it has**: files created/modified/deleted, directories created.
5. **What error conditions exist**: missing files, invalid input, bad flags, permission errors.

Read the main function and command definitions:

Use Grep to search for flag/cobra/urfave/os.Args/os.Stdin/os.Stdout/fmt.Print/fmt.Fprint/log/os.Exit patterns in `*.go` files within the package path.

## Step 5 -- Set Up the testscript Test Runner

Generate the Go test file that runs the txtar scripts. Place it in the package being tested or in a dedicated `_test` package.

Determine the correct location:

- If testing a `main` package: place `testscript_test.go` in that package's directory.
- If testing a command installed via `go install`: use `testscript.RunMain` to register the command.

Generate the runner file:

```go
package <pkgname>_test

import (
    "os"
    "testing"

    "github.com/rogpeppe/go-internal/testscript"
)

func TestMain(m *testing.M) {
    os.Exit(testscript.RunMain(m, map[string]func() int{
        "<command-name>": <mainFunc>,
    }))
}

func TestScript(t *testing.T) {
    testscript.Run(t, testscript.Params{
        Dir: "testdata/script",
    })
}
```

If the project already has a `TestMain`, warn the user about the conflict and suggest alternatives:
- Use a separate `_test` package.
- Use `testscript.Run` without `RunMain` and rely on `PATH` setup.

## Step 6 -- Generate txtar Test Scripts

Create test scripts in `testdata/script/`. Name each file descriptively: `<feature>_<scenario>.txtar`.

Use this structure for each txtar file:

```
# Description of what this test verifies.

# Setup: create any input files needed.
-- input.txt --
file contents here

# Execute the command and check results.
exec <command-name> [flags] [args]
stdout 'expected output pattern'
! stderr .

# Verify output files if applicable.
cmp stdout expected-output.txt
-- expected-output.txt --
expected file contents here
```

Follow these testscript conventions:

| Directive | Purpose | Example |
|---|---|---|
| `exec cmd args` | Run a command, expect success (exit 0) | `exec mycli --format json input.txt` |
| `! exec cmd args` | Run a command, expect failure (non-zero exit) | `! exec mycli --bad-flag` |
| `stdout 'pattern'` | Assert stdout matches regexp | `stdout 'processed 3 files'` |
| `stderr 'pattern'` | Assert stderr matches regexp | `stderr 'warning: deprecated'` |
| `! stdout .` | Assert stdout is empty | `! stdout .` |
| `cmp file1 file2` | Assert two files are identical | `cmp output.json expected.json` |
| `exists file` | Assert file exists | `exists output/result.txt` |
| `! exists file` | Assert file does not exist | `! exists temp/scratch.txt` |
| `env KEY=VALUE` | Set environment variable | `env HOME=/tmp/test` |
| `cd dir` | Change working directory | `cd subdir` |
| `cp src dst` | Copy a file | `cp input.txt backup.txt` |
| `mkdir dir` | Create a directory | `mkdir -p output/nested` |

Generate test scripts covering these scenario categories:

1. **Happy path**: normal usage with valid input producing expected output.
2. **Flag/argument variations**: each major flag or argument combination.
3. **Error cases**: missing required args, invalid input files, bad flag values.
4. **Edge cases**: empty input, very large input (noted with comments), unicode filenames if relevant.
5. **Exit codes**: verify non-zero exits for error conditions.

## Step 7 -- Write All Files

Write the files in this order:

1. The testscript runner Go file (`testscript_test.go`).
2. The `testdata/script/` directory structure.
3. Each txtar test script file.

Before writing, check for conflicts:

```bash
ls testdata/script/ 2>/dev/null
```

Run `gofmt` on the Go test runner file:

```bash
gofmt -w <runner_file_path>
```

## Step 8 -- Verify the Tests Run

Run the generated tests to verify they compile and pass:

```bash
cd <package_directory> && go test -run "TestScript" -v -count=1 ./... 2>&1 | tail -40
```

If tests fail:

- **Compilation error in runner**: fix the Go file and re-run.
- **Command not found in txtar**: verify the command is correctly registered in `RunMain` or available on `PATH`.
- **Assertion failures**: review whether the expected output matches actual behavior. Fix the txtar script to match reality -- the goal is to lock in **current correct behavior**, not aspirational behavior.

If `testscript` is not installed, remind the user to run `go get` and stop here.

## Step 9 -- Present Results

Report to the user:

1. The path to the test runner file.
2. The paths to all generated txtar scripts with a one-line description of each.
3. The number of test scenarios covered (happy path, errors, edge cases).
4. Whether all tests passed during verification.
5. Any `TODO` comments that need attention.

Remind the user:

"txtar script tests verify observable behavior: stdout, stderr, exit codes, and file output. If you need to test internal logic, function return values, or performance, complement these with unit tests and benchmarks. Run these tests with `go test -run TestScript -v ./path/to/package`."
