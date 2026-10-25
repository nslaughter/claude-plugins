---
name: generate-mocks
description: Generate interface mocks matching the project's existing conventions -- hand-rolled fakes, testify, or mockgen. Use when the user asks to mock, fake, or stub a Go interface for testing.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate Mocks

Generate interface mocks using the project's preferred approach. Detects existing mock conventions in the codebase and follows them. Supports hand-rolled fakes, testify/mock, and go:generate directives for mockgen/moq.

## Step 1 -- Identify the Target Interface

Check whether the user specified an interface name and file path in their prompt.

- If the user provided both, read that file and locate the interface definition.
- If the user provided only an interface name, search for it:

Use Grep to search for `type.*<InterfaceName>.*interface` in `*.go` files.

- If the user provided only a file path, read the file and list all interfaces defined in it, then ask the user which interface to mock.
- If the user provided neither, ask: "Which interface should I generate a mock for? Please provide the interface name and optionally the file path."

Once found, read the interface definition and extract:

1. **Interface name** and the package it belongs to.
2. **All methods**: name, parameters (names and types), and return values.
3. **Embedded interfaces**: resolve them recursively to get the full method set.
4. **Imports** needed by the method signatures.

## Step 2 -- Evaluate Whether Mocking Is the Right Approach

Read the code under test and evaluate whether mocking is the best fit. See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference.

### BAD candidates for mocks -- recommend alternatives instead

| Subject | Why Mocks Are Wrong | Recommend Instead |
|---|---|---|
| Concrete types (not interfaces) | Go mocks implement interfaces. If the dependency is a concrete type, you can't mock it without introducing an interface -- which may be over-engineering. Test with the real type instead. | **Table tests** with the real dependency -- offer `/generate-table-tests` |
| Trivial interfaces (1 method, simple contract) | A full mock with call tracking is heavier than an inline anonymous struct literal. | Inline fake: `svc := &struct{ MyInterface }{ ... }` |
| Testing the mock itself | If you're writing tests to verify that the mock behaves correctly, you're testing infrastructure, not your code. | Step back and test the real behavior |

If the subject matches a BAD row above, redirect the user using this pattern:

> "Mock tests isolate code from its dependencies by replacing interfaces with test doubles. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

If borderline, use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with mocks" as the second.

## Step 3 -- Detect Existing Mock Conventions

Search the codebase for existing mocks to determine which approach the project uses:

### Check for testify/mock

Use Grep to search for `mock.Mock` in `*.go` files, then use Grep to search for `github.com/stretchr/testify/mock` in `*.go` files.

### Check for mockgen (gomock)

Use Grep to search for `go:generate.*mockgen` in `*.go` files, then use Grep to search for `golang/mock|go.uber.org/mock` in `*.go` files.

### Check for moq

Use Grep to search for `go:generate.*moq` in `*.go` files.

### Check for hand-rolled fakes

Use Glob to find files matching `**/*fake*` and `**/*stub*` (excluding vendor). Then use Grep to search for `type.*Fake|type.*Stub|type.*Mock` in `*_test.go` files.

### Check go.mod for testing dependencies

Use Grep to search for `testify|gomock|go.uber.org/mock|moq` in `go.mod`.

### Decision Matrix

| Evidence Found | Convention to Follow |
|---|---|
| `testify/mock` imports in test files | Generate a testify mock |
| `go:generate mockgen` directives | Generate a mockgen directive |
| `go:generate moq` directives | Generate a moq directive |
| Hand-rolled fakes/stubs with `Fake*` or `Stub*` naming | Generate a hand-rolled fake |
| No existing mocks found | Default to hand-rolled fake (no external dependencies) |
| Mixed conventions | Ask the user which approach to use |

## Step 4 -- Generate the Mock

Based on the detected convention, generate the appropriate mock implementation.

### Option A: Hand-Rolled Fake

Generate a struct that implements the interface with configurable function fields. This is the most flexible approach and requires no external dependencies.

File name: `fake_<interface>_test.go` or `<interface>_fake_test.go` (match existing naming pattern).

```go
package <pkgname>

// Fake<InterfaceName> is a test fake for <InterfaceName>.
type Fake<InterfaceName> struct {
    // Function fields -- set these in your test to control behavior.
    <MethodName>Func func(<params>) (<returns>)

    // Call tracking
    <MethodName>Calls []struct {
        <ParamName> <ParamType>
        // ... one field per parameter
    }
}

// <MethodName> implements <InterfaceName>.
func (f *Fake<InterfaceName>) <MethodName>(<params>) (<returns>) {
    f.<MethodName>Calls = append(f.<MethodName>Calls, struct {
        <ParamName> <ParamType>
    }{<paramNames>})

    if f.<MethodName>Func != nil {
        return f.<MethodName>Func(<paramNames>)
    }

    // Return zero values if no func is set.
    return <zero_values>
}

// Compile-time interface check.
var _ <InterfaceName> = (*Fake<InterfaceName>)(nil)
```

For each method:
- Add a `<Method>Func` field that tests set to control the fake's behavior.
- Add a `<Method>Calls` slice that records each call for assertion purposes.
- Return zero values when `<Method>Func` is nil so the fake is safe to use without full configuration.
- Include `context.Context` parameters in the method signature but exclude them from the `Calls` struct (contexts are not comparable).

### Option B: Testify Mock

Generate a struct embedding `mock.Mock` with method implementations that delegate to `mock.Called()`.

File name: `mock_<interface>_test.go` (match existing naming pattern).

```go
package <pkgname>

import (
    "github.com/stretchr/testify/mock"
    // additional imports for param/return types
)

// Mock<InterfaceName> is a testify mock for <InterfaceName>.
type Mock<InterfaceName> struct {
    mock.Mock
}

// <MethodName> implements <InterfaceName>.
func (m *Mock<InterfaceName>) <MethodName>(<params>) (<returns>) {
    args := m.Called(<paramNames>)
    return args.Get(0).(<ReturnType1>), args.Error(1)
}

// Compile-time interface check.
var _ <InterfaceName> = (*Mock<InterfaceName>)(nil)
```

Adapt the `args.Get()` and `args.Error()` calls based on actual return types:
- Use `args.Error(n)` for `error` returns.
- Use `args.Get(n).(<Type>)` for non-interface types.
- Use `args.Bool(n)`, `args.String(n)`, `args.Int(n)` for primitive types.
- For pointer/interface returns that may be nil, use a nil-safe pattern:

```go
var r0 *SomeType
if rf, ok := args.Get(0).(func() *SomeType); ok {
    r0 = rf()
} else if args.Get(0) != nil {
    r0 = args.Get(0).(*SomeType)
}
return r0, args.Error(1)
```

### Option C: mockgen Directive

Generate a `go:generate` comment that produces the mock via mockgen.

Add the directive to the file containing the interface (or to a `generate.go` file if that pattern exists in the project):

```go
//go:generate mockgen -source=<source_file>.go -destination=mock_<interface>_test.go -package=<pkgname> <InterfaceName>
```

Or if using the reflect mode (detected from existing directives):

```go
//go:generate mockgen -destination=mock_<interface>_test.go -package=<pkgname> <module_path>/<package> <InterfaceName>
```

After adding the directive, run it:

```bash
go generate <package_path>
```

If `mockgen` is not installed, inform the user:

```
mockgen is not installed. Install it with:
  go install go.uber.org/mock/mockgen@latest
  # or: go install github.com/golang/mock/mockgen@latest (older version)
Then run: go generate ./path/to/package
```

### Option D: moq Directive

Generate a `go:generate` comment for moq:

```go
//go:generate moq -out mock_<interface>_test.go -pkg <pkgname> . <InterfaceName>
```

After adding the directive, run it:

```bash
go generate <package_path>
```

If `moq` is not installed, inform the user how to install it.

## Step 5 -- Place the Mock File

Determine where to put the generated mock:

1. **Same package as the interface** (in a `_test.go` file): preferred for internal interfaces. The mock is only available in tests.
2. **Separate `mocks/` or `mock/` package**: if the project uses this convention (check for existing `mocks/` directories). Required when multiple packages need the same mock.

Use Glob to find directories matching `**/mock*/` (excluding vendor).

Follow whatever convention already exists. If no convention exists, default to a `_test.go` file in the same package.

## Step 6 -- Write the File

Write the generated mock file. Before writing:

1. Check if the target file already exists.
2. If it does and contains a mock for the same interface, warn the user and ask whether to overwrite.
3. If it exists but has no conflict, append the new mock.

Run `gofmt` on the generated file:

```bash
gofmt -w <mock_file_path>
```

## Step 7 -- Verify Compilation

Verify the mock compiles:

```bash
cd <package_directory> && go build ./... 2>&1
```

If using a `_test.go` file:

```bash
cd <package_directory> && go test -run "^$" ./... 2>&1
```

If compilation fails, read the error, fix the generated code, and re-run.

## Step 8 -- Generate Usage Example

Provide a usage example tailored to the mock style:

### Hand-rolled fake usage

```go
func TestSomething(t *testing.T) {
    t.Parallel()

    fake := &Fake<InterfaceName>{
        <MethodName>Func: func(<params>) (<returns>) {
            return <values>, nil
        },
    }

    // Use fake in the code under test
    result := DoSomething(fake)

    // Assert the fake was called correctly
    if len(fake.<MethodName>Calls) != 1 {
        t.Errorf("expected 1 call to <MethodName>, got %d", len(fake.<MethodName>Calls))
    }
}
```

### Testify mock usage

```go
func TestSomething(t *testing.T) {
    t.Parallel()

    m := new(Mock<InterfaceName>)
    m.On("<MethodName>", <matchers>).Return(<values>, nil)

    result := DoSomething(m)

    m.AssertExpectations(t)
}
```

## Step 9 -- Present Results

Report to the user:

1. The detected mock convention and why it was chosen.
2. The path to the generated mock file.
3. The interface methods that were mocked.
4. The usage example.
5. Any compilation issues that were encountered and fixed.

If the interface was large (more than 5 methods), add a note: "This interface has N methods. Consider whether it should be split into smaller interfaces. Consumers should depend on the smallest interface that satisfies their needs. See the Go proverb: 'The bigger the interface, the weaker the abstraction.'"
