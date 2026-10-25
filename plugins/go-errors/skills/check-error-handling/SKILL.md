---
name: check-error-handling
description: Find error handling issues beyond errcheck -- swallowed errors, unchecked Close, shadowed variables, and misused Is/As
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Check Error Handling

Find error handling issues that go beyond what `errcheck` catches: errors swallowed inside goroutines, deferred `Close()` calls with unchecked errors, error values shadowed by `:=` in inner scopes, and `errors.Is`/`errors.As` used with unwrapped errors. Present findings as an actionable report.

## Step 1 -- Determine Scope

Ask the user which files or packages to analyze. Accept any of:

- A single file path
- A package path (e.g., `./internal/service/...`)
- A directory
- "all" to scan the entire module

If the user does not specify a scope, default to the current working directory recursively.

## Step 2 -- Check: Errors Swallowed in Goroutines

Search for goroutines that call error-returning functions but discard the error.

Use Grep to find goroutine launches:

```
go func\(
```

For each match, Read the surrounding code (20-30 lines). Verify the match is actual Go code (not inside a comment or string literal) before analyzing. Check for:

### Issue 2a: Error returned but not captured

```go
// BAD: error from processItem is silently discarded
go func() {
    processItem(ctx, item)  // returns error, but nobody checks
}()
```

### Issue 2b: Error captured but not sent anywhere

```go
// BAD: err is captured but dies with the goroutine
go func() {
    if err := processItem(ctx, item); err != nil {
        log.Printf("error: %v", err)  // logged but not propagated -- often acceptable
    }
}()
```

For 2b, only flag it if the error is not logged, not sent to an error channel, and not recorded in any way. Logging is acceptable in goroutines since there is no caller to return to.

### Issue 2c: Error channel not checked

```go
// BAD: error channel created but never read
errCh := make(chan error, 1)
go func() {
    errCh <- doWork(ctx)
}()
// errCh is never read
```

Use Grep to find `chan error` declarations and verify they are read from (`<-errCh` or `select` with the channel).

## Step 3 -- Check: Unchecked Deferred Close

Search for deferred `Close()` calls where the error is not checked.

Use Grep to find:

```
defer .*\.Close\(\)
```

### Issue 3a: Bare defer Close

```go
// BAD: Close error is silently discarded
defer f.Close()
```

This should be:

```go
// GOOD: error checked (common pattern for writable resources)
defer func() {
    if cerr := f.Close(); cerr != nil {
        err = errors.Join(err, cerr)
    }
}()
```

Or at minimum:

```go
// ACCEPTABLE: error logged
defer func() {
    if err := f.Close(); err != nil {
        log.Printf("close error: %v", err)
    }
}()
```

### Severity guidance

- **High**: Unchecked `Close()` on writable resources (`os.File` opened for writing, `*sql.Tx`, `*http.Response.Body` after reading, `io.WriteCloser`). Data loss is possible.
- **Medium**: Unchecked `Close()` on readable resources (`os.File` opened for reading, `*sql.Rows`). Less likely to cause data loss but can leak resources.
- **Low**: Unchecked `Close()` on network connections in short-lived processes.

Also search for other common deferred calls that return errors:

```
defer .*\.Rollback\(\)
defer .*\.Flush\(\)
defer .*\.Sync\(\)
```

## Step 4 -- Check: Error Variable Shadowing

Search for cases where an outer `err` variable is shadowed by `:=` in an inner scope.

Use Grep to find functions where `err` is declared and then re-declared in an inner block:

```
:= .+; err != nil
```

For each file with error returns, Read the file and look for this pattern:

### Issue 4a: Shadowing with := in if block

```go
// BAD: inner err shadows outer err
func process() error {
    result, err := step1()      // outer err
    if err != nil {
        return err
    }
    if something {
        result, err := step2()  // SHADOWS outer err with :=
        if err != nil {
            return err          // returns inner err, but outer err is unchanged
        }
        _ = result
    }
    return nil                  // outer err was never set by step2
}
```

### Issue 4b: Shadowing in for/switch/select blocks

```go
// BAD: err inside for loop shadows outer err
var err error
for _, item := range items {
    result, err := process(item)  // shadows outer err
    if err != nil {
        break
    }
    _ = result
}
return err  // always nil -- inner err was a different variable
```

To detect this:

1. Use Grep to find files containing `func .* error` (functions returning error).
2. Read each file and find functions that return `error`.
3. Within each function body, track `err` declarations: note the first `:=` that introduces `err`, then flag any subsequent `:=` for `err` inside nested blocks (`if`, `for`, `switch`, `select`) where the outer `err` is already in scope.
4. Distinguish intentional new variables (e.g., `err2 :=`) from accidental shadowing (same name `err`).

This analysis requires reading full function bodies since Grep alone cannot track variable scopes.

## Step 5 -- Check: errors.Is/errors.As with Unwrapped Errors

Search for `errors.Is` and `errors.As` calls that compare against errors that are never wrapped.

Use Grep to find:

```
errors\.Is\(
errors\.As\(
```

For each call, check:

### Issue 5a: errors.Is with a non-sentinel target

```go
// BAD: comparing with a fresh error -- will never match
if errors.Is(err, errors.New("not found")) {
    // This NEVER matches because errors.New creates a new pointer each time
}
```

The target of `errors.Is` must be a package-level `var` (sentinel), not an inline `errors.New`.

### Issue 5b: errors.Is target that is never wrapped

```go
// SUSPICIOUS: if ErrNotFound is never wrapped into other errors,
// errors.Is will only match exact equality -- same as ==
var ErrNotFound = errors.New("not found")

// If nothing in the codebase does fmt.Errorf("...: %w", ErrNotFound),
// then errors.Is(err, ErrNotFound) is equivalent to err == ErrNotFound
```

To check this:

1. Find all sentinel error declarations (`var Err.* = errors.New`).
2. For each sentinel, search for it being wrapped with `%w`:
   ```
   fmt\.Errorf.*%w.*ErrNotFound
   ```
   Also search for types with `Unwrap()` that return it.
3. If a sentinel is used with `errors.Is` but never wrapped anywhere, flag it as suspicious (not necessarily wrong, but worth reviewing).

### Issue 5c: errors.As with wrong target type

```go
// BAD: target must be a pointer to the error type, not the type itself
var target ValidationError  // should be *ValidationError
if errors.As(err, &target) {
    // ...
}
```

Check that `errors.As` targets are pointers to error types or interfaces.

## Step 6 -- Present Report

Compile all findings into a structured report grouped by category and severity.

```
=== Error Handling Analysis Report ===

Scope: ./internal/...
Files scanned: 47
Issues found: 12

--- ERRORS SWALLOWED IN GOROUTINES (3 issues) ---

[HIGH] internal/worker/processor.go:42
  Goroutine calls processItem() which returns error, but error is discarded.
  go func() {
      processItem(ctx, item)  // error not checked
  }()
  Fix: Send error to an error channel or use an errgroup.

[MEDIUM] internal/service/notifier.go:88
  Error channel created at line 85 but never read from.
  errCh := make(chan error, 1)  // line 85, never consumed
  Fix: Read from errCh after goroutine completes.

--- UNCHECKED DEFERRED CLOSE (4 issues) ---

[HIGH] internal/storage/writer.go:23
  defer f.Close() on file opened for writing.
  Fix: defer func() { err = errors.Join(err, f.Close()) }()

[MEDIUM] internal/handler/download.go:45
  defer resp.Body.Close() -- error discarded.
  Fix: defer func() { _ = resp.Body.Close() }() (explicit discard) or check error.

--- ERROR VARIABLE SHADOWING (2 issues) ---

[HIGH] internal/service/order.go:67
  `err` declared at line 55, shadowed by := at line 67 inside if block.
  Outer err is never updated by step2 result.
  Fix: Use = instead of := at line 67.

--- ERRORS.IS/AS MISUSE (3 issues) ---

[HIGH] internal/handler/api.go:34
  errors.Is(err, errors.New("not found")) -- inline errors.New never matches.
  Fix: Use a package-level sentinel error variable.

[LOW] internal/service/user.go:89
  errors.Is(err, ErrNotFound) but ErrNotFound is never wrapped anywhere in the codebase.
  This works but is equivalent to err == ErrNotFound.
  Consider: Either wrap ErrNotFound in lower layers or use == for clarity.

=== Summary ===
  High:   5
  Medium: 4
  Low:    3
  Total: 12
```

## Step 7 -- Offer Fixes

After presenting the report, ask the user: "Would you like me to fix any of these issues? You can specify by category, severity, or individual issue."

If the user requests fixes:

- **Goroutine errors**: Suggest and apply `errgroup` pattern or error channel pattern.
- **Unchecked Close**: Apply the `defer func() { err = errors.Join(err, f.Close()) }()` pattern.
- **Shadowing**: Replace `:=` with `=` where the outer `err` should be reused.
- **errors.Is misuse**: Extract inline `errors.New` to package-level sentinels.

After applying fixes, run:

```bash
go build ./path/to/package/...
go vet ./path/to/package/...
```

If build or vet fails after a fix, revert that specific change using Edit and report the failure to the user. Do not leave the code in a broken state.

## Rules

- This skill is a READ-ONLY analysis by default. Do NOT modify any files unless the user explicitly requests fixes.
- Report issues with specific file paths and line numbers.
- Include the offending code snippet in each finding for context.
- Classify severity as HIGH, MEDIUM, or LOW based on the likelihood of data loss or bugs.
- Do NOT report issues that `errcheck` already catches (simple unchecked error returns). Focus on the deeper issues that static analysis tools miss.
- Do NOT flag explicit error discards with `_ = f.Close()` -- the developer intentionally discarded the error.
- Do NOT flag goroutines where the error is logged -- logging is a valid handling strategy in goroutines.
- When checking for shadowing, be careful to distinguish between intentional new variables and accidental shadowing. Only flag cases where the outer `err` appears to be the intended target.
