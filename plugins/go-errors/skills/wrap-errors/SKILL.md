---
name: wrap-errors
description: Scan for bare `return err` statements and rewrite them with contextual wrapping using fmt.Errorf
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Wrap Errors

Scan Go source files for bare `return err` statements and rewrite them to `fmt.Errorf("context: %w", err)` with contextual messages derived from the enclosing function name and parameters. Respect existing wrapping and skip already-wrapped returns.

## Step 1 -- Determine Scope

Ask the user which files or packages to scan. Accept any of:

- A single file path (e.g., `./handler.go`)
- A package path (e.g., `./internal/service/...`)
- A directory (e.g., `./cmd/server/`)
- "all" to scan the entire module

If the user does not specify a scope, default to the current working directory recursively (`./...`).

## Step 2 -- Find Bare Error Returns

Search for bare `return err` and `return ..., err` patterns that are NOT already wrapped. Use Grep to find candidates.

### Patterns to match (bare returns)

These patterns indicate errors returned without added context:

```
return err$
return err\)
return .*, err$
return .*, err\)
```

### Patterns to EXCLUDE (already wrapped)

Skip lines that already wrap the error:

- `fmt.Errorf(` with `%w`
- `errors.Wrap(` or `errors.Wrapf(`
- `errors.WithMessage(` or `errors.WithMessagef(`
- `errors.WithStack(`
- Any function call that takes `err` as an argument and returns an error (custom wrapping)

For each candidate file, use Read to load the file and confirm that the `return err` is truly bare -- not inside a comment, not inside a string literal, not inside an `fmt.Errorf`, not part of a wrapping expression, and not a simple error variable pass-through in a one-line helper.

## Step 3 -- Extract Context for Wrapping

For each bare `return err` found, determine the wrapping context by reading the enclosing function:

1. **Function name**: Use the `func` declaration line to get the function or method name.
2. **Receiver type** (if method): Include the type name for methods (e.g., `UserService.Create`).
3. **Key parameters**: Include relevant parameters that add debugging context. Prefer:
   - String identifiers (names, IDs, keys)
   - Numeric identifiers
   - Omit large structs, slices, contexts, and io.Readers
4. **Operation being performed**: Infer from the function call on the line preceding the error check. Use the called function or method name as the operation (e.g., `s.repo.Find` → "finding", `os.ReadFile` → "reading file", `json.Unmarshal` → "unmarshaling"). If the preceding call is ambiguous, use just the function/method name without further elaboration.

### Wrapping message format

Use this format for the `fmt.Errorf` message:

```go
// For functions:
fmt.Errorf("functionName: %w", err)

// For methods:
fmt.Errorf("TypeName.MethodName: %w", err)

// When a useful parameter adds context:
fmt.Errorf("functionName(%s): %w", paramName, err)

// When the operation is clear from surrounding code:
fmt.Errorf("functionName: doing something: %w", err)
```

Examples:

```go
// Before:
func (s *UserService) GetByID(ctx context.Context, id string) (*User, error) {
    user, err := s.repo.Find(id)
    if err != nil {
        return nil, err  // <-- bare return
    }
    return user, nil
}

// After:
func (s *UserService) GetByID(ctx context.Context, id string) (*User, error) {
    user, err := s.repo.Find(id)
    if err != nil {
        return nil, fmt.Errorf("UserService.GetByID(%s): %w", id, err)
    }
    return user, nil
}
```

```go
// Before:
func loadConfig(path string) (*Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, err  // <-- bare return
    }
    var cfg Config
    if err := json.Unmarshal(data, &cfg); err != nil {
        return nil, err  // <-- bare return
    }
    return &cfg, nil
}

// After:
func loadConfig(path string) (*Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("loadConfig: reading file: %w", err)
    }
    var cfg Config
    if err := json.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("loadConfig: unmarshaling config: %w", err)
    }
    return &cfg, nil
}
```

## Step 4 -- Present Changes Before Applying

Before modifying any file, present a summary of all proposed changes to the user:

```
File: internal/service/user.go
  Line 42: return nil, err  -->  return nil, fmt.Errorf("UserService.GetByID(%s): %w", id, err)
  Line 67: return nil, err  -->  return nil, fmt.Errorf("UserService.Create: validating input: %w", err)

File: internal/handler/auth.go
  Line 23: return err  -->  return fmt.Errorf("handleLogin: authenticating: %w", err)

Total: 3 bare returns in 2 files
```

Ask the user: "Apply all changes, select specific files, or cancel?"

## Step 5 -- Apply Changes

For each approved change:

1. Use Edit to replace the bare `return err` with the wrapped version.
2. Check if `fmt` is already imported in the file. If not, add it to the import block.
3. If the file uses named imports for `fmt` (rare but possible), respect the alias.

After applying, verify the file compiles:

```bash
go build ./path/to/package/...
```

If compilation fails, identify which change caused it by running `go build` after each file's changes (not just once at the end). Revert the failing file's changes using Edit and report the failure to the user. Do not leave any file in a non-compiling state.

## Step 6 -- Report

Present a final summary:

- Number of files modified
- Number of bare returns wrapped
- Number of files skipped (already wrapped)
- Any compilation errors encountered

## Rules

- NEVER wrap errors that are already wrapped. When in doubt, skip.
- NEVER change the error variable name or the control flow.
- NEVER modify `return nil` (no error to wrap).
- NEVER wrap sentinel errors like `return ErrNotFound` -- only wrap `err` variables.
- ALWAYS preserve the existing return structure (number of return values, order).
- ALWAYS ensure `fmt` is imported after adding `fmt.Errorf`.
- If a function has multiple bare returns, each should get a distinct context message describing what operation failed at that point.
- If the function is trivially short (single `return err` with no other logic), use just the function name without an operation description.
