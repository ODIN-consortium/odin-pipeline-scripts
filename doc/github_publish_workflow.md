# Publishing a Clean Snapshot to GitHub

This document describes how to publish a clean, history-free snapshot of an internally developed repository to a public GitHub repository. The approach is designed for projects that:

- Are developed on an internal GitLab instance
- Contain internal artefacts (build outputs, large binaries, internal scripts, PDF docs) that should not appear on GitHub
- Want GitHub to show only release-to-release history, not internal development commits

The same pattern applies to any repo in this project (e.g. `pipeline_scripts`, `odin_pipeline`).

---

## Concept

Three branches are involved:

```
main  ──cherry-pick──▶  <prerelease>  ──file copy──▶  <publish>  ──push──▶  GitHub
```

| Branch | Purpose |
|---|---|
| `main` | Internal development on GitLab. Full history. |
| `<prerelease>` | Clean-room staging branch. Internal artefacts removed. Safe to publish. |
| `<publish>` | Orphan branch (no shared history with main). One commit per release. |

The key principle: **never `git merge` or `git rebase` into `<publish>`**. Always use a file-level copy (`git checkout <branch> -- .`). This ensures that no internal history, removed files, or credentials can leak into the GitHub repo.

---

## One-time setup

Run these steps once per repository.

### 1. Add the GitHub remote

```bash
git remote add github https://github.com/<org>/<repo>.git
```

You can verify remotes with `git remote -v`. Your internal GitLab remote stays as `origin`.

### 2. Prepare the prerelease branch

Create a branch off `main` that represents the public-safe state of the code. On this branch:

- Remove any internal artefacts (PDFs, build outputs, internal scripts, credentials, large binaries that should not be public)
- Fix any paths or references that pointed at internal-only files
- Update `.gitignore` to exclude those artefacts permanently

```bash
git checkout -b github-prerelease
# ... remove/fix files ...
git add -A
git commit -m "Prepare prerelease: remove internal artefacts"
git push origin github-prerelease
```

### 3. Create the orphan publish branch

An orphan branch has no parent commits — it is a completely fresh history. Create it from the current state of `github-prerelease`:

```bash
git checkout github-prerelease
git checkout --orphan github-publish
git add -A
git commit -m "Initial public snapshot"
```

### 4. Force-push to GitHub (first time only)

```bash
git push github github-publish:main --force
```

The `--force` is required only on the first push because the GitHub repo may have an unrelated initial commit. After this, all subsequent pushes are normal (no force).

---

## Publishing a new release

When you are ready to publish a new snapshot (e.g. after several internal commits on `main`):

### 1. Bring changes into the prerelease branch

Cherry-pick or merge the relevant commits from `main` into `github-prerelease`. Only include changes that are safe to publish.

```bash
git checkout github-prerelease

# Cherry-pick specific commits by hash
git cherry-pick <commit-hash>

# Or cherry-pick a range
git cherry-pick <oldest-hash>^..<newest-hash>
```

If a cherry-picked commit touches files that don't exist on `github-prerelease` (because they were removed), resolve the conflict by accepting the deletion.

### 2. File-copy onto the publish branch

```bash
git checkout github-publish

# Copy the entire working tree from prerelease — files only, no history
git checkout github-prerelease -- .

git add -A
git commit -m "Release vX.Y snapshot"
```

The `git checkout <branch> -- .` command copies files from the named branch into your working tree and index. It does **not** bring across any commits or history.

### 3. Push to GitHub

```bash
git push github github-publish:main
```

No `--force` needed after the first push, as `github-publish` grows forward with each release.

---

## What NOT to do

| Command | Why to avoid |
|---|---|
| `git merge main` on `github-publish` | Would pull in all internal history and potentially removed files |
| `git rebase` onto `github-publish` | Same problem |
| `git push --mirror` | Pushes all local branches and history to the remote — exposes everything |
| `git push origin github-publish` | Pushes to GitLab, not GitHub — use `github` as the remote name |

---

## Checking what will be published

Before pushing, you can inspect the diff between the last GitHub snapshot and the current state:

```bash
# See what files changed since last snapshot
git diff HEAD~1 --name-only

# See the full diff
git diff HEAD~1
```

Or compare directly against what is on GitHub:

```bash
git fetch github
git diff github/main github-publish
```

---

## Summary of branch commands

```bash
# Switch between branches
git checkout main              # internal development
git checkout github-prerelease # clean-room staging
git checkout github-publish    # snapshot for GitHub

# One-liner to update github-publish from prerelease and push
git checkout github-publish && \
  git checkout github-prerelease -- . && \
  git add -A && \
  git commit -m "Release vX.Y snapshot" && \
  git push github github-publish:main
```
