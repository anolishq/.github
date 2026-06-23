# Shared task runner for anolis providers. Copy to `justfile` at the repo root and
# set `preset` to the repo's primary CMake configure/test preset.
#
# Standard recipes (match the org convention): setup, fmt, fmt-check, lint, check, test.

# Primary CMake preset — override per repo (e.g. ci-linux-release).
preset := "ci-linux-release"

# C++ sources tracked by git (excludes generated build/ output).
cpp_files := "git ls-files '*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx'"

# List available recipes.
default:
    @just --list

# Configure (vcpkg deps resolve during CMake configure).
setup:
    cmake --preset {{preset}}

# Install the pinned pre-commit hooks (one-time per clone).
hooks:
    pre-commit install

# Format C++ sources in place via the pinned pre-commit clang-format.
fmt:
    pre-commit run clang-format --all-files

# Verify formatting via the pinned pre-commit hooks (CI gate).
fmt-check:
    pre-commit run --all-files

# Static analysis over the compile database (requires a configured build dir).
lint:
    run-clang-tidy -p build/{{preset}} $({{cpp_files}})

# CI-equivalent: formatting + lint.
check: fmt-check lint

# Build and run the test suite.
test:
    cmake --build --preset {{preset}} --parallel
    ctest --preset {{preset}} --output-on-failure
