---
name: local-build
description: Detect build tool, run build, parse errors, fix and rebuild — max 3 cycles
---

## Before You Start

- [ ] Verify `$TARGET_REPO_PATH` is set and points to the correct project root
- [ ] Confirm you are on the correct git branch (building the wrong branch wastes time)
- [ ] Check available disk space — build artifacts can be large (especially Docker images, Maven `.m2`, `node_modules`)
- [ ] Verify required build tools are installed (Java, Node, Rust, Go, Python) at the expected version
- [ ] If the project uses a lock file (`package-lock.json`, `poetry.lock`, `Cargo.lock`), ensure it is present and up to date

## Workflow

1. **Check for a custom build command.** If `$CODE_AGENTS_BUILD_CMD` is set, use it directly. Otherwise, detect the build tool from the project root.

2. **Detect the build tool.** Check for these files in order:
   - `pom.xml` → Maven: `mvn clean compile -q`
   - `build.gradle` or `build.gradle.kts` → Gradle: `./gradlew build`
   - `package.json` → npm: `npm run build` (or `npm install` if no build script)
   - `Cargo.toml` → Rust: `cargo build`
   - `go.mod` → Go: `go build ./...`
   - `pyproject.toml` → Python: `poetry install` or `pip install -e .`
   - `Makefile` → Make: `make`

3. **Run the build command.** Execute the detected or custom build command:
   ```bash
   # Example for Maven
   cd $TARGET_REPO_PATH && mvn clean compile -q
   ```

4. **Parse build output for errors.** If the build fails:
   - Extract error messages, file paths, and line numbers
   - Identify the type of error: compilation error, missing dependency, config issue
   - For compilation errors: read the source file at the error line and fix the code
   - For missing dependencies: add the dependency to the build file (pom.xml, package.json, etc.)
   - For config issues: check build config files and fix settings

5. **Fix the errors and rebuild.** Apply fixes and run the build again:
   - Fix only the build errors — do not refactor or change unrelated code
   - Re-run the same build command from step 3

6. **Repeat steps 4-5 until the build succeeds.** Maximum 3 cycles. If the build still fails after 3 cycles:
   - Report all remaining errors with file paths and line numbers
   - Show what you tried and why it did not work
   - Ask the user for guidance — do not keep looping

7. **Report success.** When the build passes, confirm:
   - Build tool and command used
   - Number of cycles needed
   - Any warnings that should be addressed later

## Build Optimization Hints

When builds are slow, consider these trade-offs:

| Technique | When to Use | Trade-off |
|-----------|-------------|-----------|
| **Incremental build** (`mvn compile` vs `mvn clean compile`) | When only source files changed, not dependencies | Faster, but stale artifacts can cause confusing errors |
| **Parallel build** (`mvn -T 1C`, `gradle --parallel`) | Multi-module projects with independent modules | Faster, but can mask ordering-dependent bugs |
| **Skip tests in build** (`mvn compile -DskipTests`) | When you only need to verify compilation, not correctness | Faster, but tests should be run separately before pushing |
| **Offline mode** (`mvn -o`, `npm --prefer-offline`) | When all dependencies are cached locally | Faster, but will fail if a new dependency was added |
| **Docker layer caching** | When Dockerfile has not changed base layers | Dramatically faster image builds |

Only suggest these to the user — never silently skip tests or use offline mode by default.

## Dependency Verification

After a successful build, verify:
- [ ] No dependency version conflicts or forced resolutions in the output
- [ ] No deprecated dependency warnings that indicate upcoming breakage
- [ ] Lock file is consistent (if a lock file exists, `git diff` should show no changes to it after build)
- [ ] No new vulnerabilities introduced — if the build tool supports audit (`npm audit`, `mvn dependency-check:check`), note any HIGH/CRITICAL findings

## Risk Assessment

| Risk | Signs | Mitigation |
|------|-------|------------|
| **Stale cache** | Build passes locally but fails in CI | Use `clean` build after dependency changes |
| **Version mismatch** | "Works on my machine" — different JDK, Node, or Python version | Check `.tool-versions`, `.nvmrc`, `Dockerfile` for expected versions |
| **Missing env vars** | Build fails with "undefined variable" or config errors | Verify all required env vars are set before building |
| **Transitive dependency conflict** | Runtime `ClassNotFoundException` or `ModuleNotFoundError` despite successful build | Check dependency tree for version conflicts |

## Definition of Done

- [ ] Build completes with exit code 0
- [ ] No compilation errors or warnings that indicate real problems (unused imports are OK, unchecked casts are not)
- [ ] Build artifacts are generated in the expected location
- [ ] If Docker: image is tagged correctly and can start without immediate crash
- [ ] All warnings reviewed — none represent security issues or upcoming breakage
