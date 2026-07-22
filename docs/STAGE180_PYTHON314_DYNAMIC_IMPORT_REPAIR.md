# Stage180 Python 3.14 Dynamic Import Repair

## Root cause

Stage180 loaded the Stage178 runtime with `module_from_spec()` and immediately
called `exec_module()`. The module was not yet present in `sys.modules`.

Python 3.14 `dataclasses` inspects `sys.modules[cls.__module__]` while applying
`@dataclass`. Because the Stage178 module was absent, the import failed before
the shadow cycle could start.

## Repair

The module is now registered in `sys.modules` before execution. If execution
fails, the prior module state is restored.

## Regression coverage

The package includes:

- a temporary dynamically imported module with `@dataclass`;
- direct import of the exact Stage178 runtime source used to build Stage180;
- the existing Stage180 unit suite;
- compile, clean extraction and retest.
