---
name: find-coverage-gaps
description: Run coverage analysis and identify untested code paths prioritized by complexity and change frequency. Use when the user asks to find coverage gaps, improve test coverage, or identify untested code in a Go package.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Find Coverage Gaps

Run `go test -coverprofile` and identify untested code paths. Prioritize gaps by cyclomatic complexity and change frequency. Distinguish between high-risk uncovered code (error handling, branching logic) and low-risk code (simple getters, generated code).

## Step 1 -- Determine Scope

Check whether the user specified a target in their prompt:

- **Specific package**: e.g., `./internal/parser` -- analyze just that package.
- **Specific file**: e.g., `parser.go` -- analyze the package containing that file, filter results to that file.
- **No target specified**: ask the user: "Which package or directory should I analyze for coverage gaps? You can specify a package path (e.g., `./internal/...`), a specific file, or `.` for the current directory."

## Step 2 -- Run Coverage Analysis

Run tests with coverage profiling for the target scope:

```bash
cd <project_root> && go test -coverprofile=coverage.out -covermode=count <target_package> 2>&1
```

If tests fail, **stop here**. Report the test failures to the user and use AskUserQuestion to ask: "Tests failed. Would you like to proceed with partial coverage results (unreliable), or fix the failing tests first?" **Do not continue to the next step** until the user responds. If the user chooses to fix tests, stop the workflow entirely. If the user chooses to proceed, note prominently in the final report that coverage data is from a failing test run and may be unreliable.

Parse the summary coverage percentage from the output.

Then generate an HTML coverage report for reference:

```bash
go tool cover -html=coverage.out -o coverage.html
```

And extract per-function coverage:

```bash
go tool cover -func=coverage.out
```

## Step 3 -- Analyze and Prioritize Gaps

Parse `coverage.out` for lines with count `0`. Read each uncovered block's source to understand what it does, then classify:

- **High-priority**: error handling, branching logic, validation, edge cases, security-relevant code.
- **Low-priority**: simple getters/setters, generated code, `String()`/`Error()` formatters, debug/logging.

Exclude generated files — look for `// Code generated` or `DO NOT EDIT` in the first few lines, and skip files matching `*_gen.go`, `*.pb.go`, `*_string.go`, `mock_*.go`, `zz_generated_*.go`.

For high-priority gaps, estimate complexity (branching, loops, conditions) and check recent change frequency with `git log --oneline --since="3 months ago" --diff-filter=M -- <file>`. Sort gaps by complexity × change-frequency (highest risk first).

## Step 4 -- Compile the Report

Present findings to the user in a prioritized table format:

```
## Coverage Summary

Overall coverage: XX.X%
Packages analyzed: N
Files with gaps: N

## High-Priority Coverage Gaps

Sorted by: complexity x change-frequency (highest risk first)

### 1. path/to/file.go -- FunctionName (lines XX-YY)
   Category: Error handling
   Complexity: High (N branches)
   Change frequency: N commits in 3 months
   Uncovered code:
   ```go
   if err != nil {
       return fmt.Errorf("failed to process: %w", err)
   }
   ```
   Suggested test: Test with an input that triggers this error path.

### 2. ...
```

Then list low-priority gaps separately:

```
## Low-Priority Gaps (informational)

These uncovered blocks are low-risk and can be deferred:
- path/to/file.go:XX -- simple getter Name()
- path/to/generated.pb.go -- generated code (excluded)
```

For the top 5 highest-priority gaps, include concrete test case suggestions in table-driven test struct literal style, specific enough to paste into an existing test.

## Step 5 -- Clean Up

Remove the generated coverage files:

```bash
rm -f coverage.out coverage.html
```

Let the user know: "The coverage profile has been cleaned up. To regenerate it, run `go test -coverprofile=coverage.out <package>`. The HTML report was saved to `coverage.html` if you want to browse coverage visually."

## Tips

- If the user wants to improve coverage for a specific gap, suggest using the `generate-table-tests` skill to scaffold tests for the uncovered function.
- If coverage is already high (>80%) but specific critical paths are uncovered, focus the report on those critical paths rather than listing every uncovered line.
- If the project uses build tags, remind the user that coverage may vary with different tag sets.
