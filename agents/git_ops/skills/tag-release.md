---
name: tag-release
description: Version tagging with semantic versioning and changelog generation from conventional commits
---

## Before You Start

- Confirm the version bump type: **major**, **minor**, or **patch**.
- Ensure you are on the correct branch (typically `main`) and working tree is clean.
- Fetch latest tags from remote so version parsing is accurate.

## Workflow

1. **Fetch latest tags from remote.**
   ```bash
   cd ${TARGET_REPO_PATH} && git fetch --tags
   ```

2. **Find the current latest version tag.**
   ```bash
   cd ${TARGET_REPO_PATH} && git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1
   ```
   If no tags exist, start from `v0.0.0`.

3. **Parse and bump the version** using semantic versioning:
   - **patch** (bug fixes): `v1.2.0` -> `v1.2.1`
   - **minor** (new features, backward compatible): `v1.2.0` -> `v1.3.0`
   - **major** (breaking changes): `v1.2.0` -> `v2.0.0`

4. **Generate changelog** from conventional commits since the last tag.
   ```bash
   cd ${TARGET_REPO_PATH} && git log LAST_TAG..HEAD --pretty=format:"%s (%h)" --no-merges
   ```

5. **Classify commits** by conventional commit prefix:
   - `feat:` -> Features
   - `fix:` -> Bug Fixes
   - `docs:` -> Documentation
   - `chore:` -> Maintenance
   - `refactor:` -> Refactoring
   - `test:` -> Tests
   - `BREAKING CHANGE:` or `!:` -> Breaking Changes

6. **Format the changelog:**
   ```
   ## vX.Y.Z (YYYY-MM-DD)

   ### Features
   - Add payment retry logic (abc1234)

   ### Bug Fixes
   - Fix null pointer in order service (def5678)

   ### Breaking Changes
   - Remove deprecated /v1/legacy endpoint (ghi9012)

   ### Maintenance
   - Update dependencies (jkl3456)
   ```

7. **Show the changelog to the user** and confirm before tagging.

8. **Create an annotated tag** with the changelog as the message.
   ```bash
   cd ${TARGET_REPO_PATH} && git tag -a vX.Y.Z -m "Release vX.Y.Z

   CHANGELOG_CONTENT"
   ```

9. **Push the tag to remote.**
   ```bash
   cd ${TARGET_REPO_PATH} && git push origin vX.Y.Z
   ```

10. **Report the release:**
    - Tag name and commit it points to.
    - Full changelog.
    - Remote push confirmation.

## Definition of Done

- Version correctly bumped following semantic versioning rules.
- Changelog generated from conventional commits and included in tag annotation.
- Annotated tag created on the correct commit (HEAD of main).
- Tag pushed to remote origin.
- User confirmed the changelog and version before tagging.
