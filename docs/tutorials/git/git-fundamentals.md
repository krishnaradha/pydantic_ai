# Git Fundamentals

A beginner's guide to Git — what it is, why it exists, and the commands
you'll actually use day to day.

## What is Git, and why do we need it?

Git is a **version control system** — it tracks changes to files over time,
so you can:

- See the full history of every change ever made to a file
- Go back to any previous version if something breaks
- Work on new features without touching the working code, then merge them in
- Collaborate with other people on the same codebase without overwriting
  each other's work

Without Git, "collaboration" usually means emailing zip files around named
`project_final_v3_ACTUALLY_FINAL.zip`. Git replaces that with a system that
tracks exactly what changed, who changed it, and when.

**Git vs. GitHub** — these are not the same thing:
- **Git** is the tool that runs on your computer and tracks history.
- **GitHub** (or GitLab, Bitbucket, etc.) is a website that *hosts* a copy of
  your Git history in the cloud, so you can share it and collaborate with
  others.

You can use Git entirely on your own machine with no GitHub account at all.
GitHub just makes sharing and backup easy.

## The core idea: snapshots, not diffs

Git doesn't store a list of file edits — it stores **snapshots**. Every time
you *commit*, Git takes a picture of your entire project at that moment and
saves it. Moving between commits is like flipping through a photo album of
your project's history.

## The three areas

Understanding Git means understanding three places your files can be:

```
Working Directory  →  Staging Area  →  Repository (committed history)
    (edit files)        (git add)         (git commit)
```

1. **Working directory** — the actual files on your disk, as you're editing them.
2. **Staging area** (a.k.a. "the index") — a holding area where you put the
   changes you want to include in your *next* commit. This lets you commit
   only some of your changes, not everything you've touched.
3. **Repository** — the permanent, saved history. Once something is
   committed, it's part of the project's timeline.

## Getting started

### Install Git

```bash
git --version   # check if it's already installed
```

If not installed: `brew install git` (Mac), or download from git-scm.com.

### One-time setup

Git needs to know who you are, since every commit is signed with a name/email:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

### Starting a repository

Two ways to start:

**Option A — turn an existing folder into a Git repo:**
```bash
cd my-project
git init
```

**Option B — copy (clone) an existing repo from somewhere else (e.g. GitHub):**
```bash
git clone https://github.com/someuser/somerepo.git
```

## The everyday workflow

This is the loop you'll repeat constantly:

```bash
# 1. Check what's changed
git status

# 2. See the actual line-by-line changes
git diff

# 3. Stage the files you want to commit
git add filename.py
# or stage everything changed:
git add .

# 4. Commit — save a snapshot with a message describing the change
git commit -m "Add user login validation"

# 5. Push — upload your commits to the remote (e.g. GitHub)
git push
```

### `git status` — your most-used command

Run this constantly. It tells you:
- Which files are modified but not staged
- Which files are staged and ready to commit
- Which files are untracked (new, Git doesn't know about them yet)

### `git add` — staging changes

```bash
git add file1.py file2.py   # stage specific files
git add .                   # stage everything in the current directory
git add -p                  # interactively choose which chunks to stage
```

### `git commit` — saving a snapshot

```bash
git commit -m "Short summary of what changed"
```

**Good commit messages** describe *why*, not just *what* — "Fix crash when
cart is empty" is more useful than "fix bug." Keep the first line under ~70
characters; add more detail below it if needed.

### `git log` — viewing history

```bash
git log                 # full history
git log --oneline       # condensed, one line per commit
git log --graph --all   # visualize branches
```

## Branches

A branch is an independent line of development. The default branch is
usually called `main` (or historically `master`). Branches let you work on
a new feature without touching the working version of the code.

```bash
git branch                      # list branches
git branch new-feature          # create a branch
git checkout new-feature        # switch to it
# — or do both in one step:
git checkout -b new-feature

# newer syntax (Git 2.23+), does the same thing:
git switch -c new-feature
```

Work happens on the branch exactly like before — `add`, `commit`, etc. Once
the feature is ready, merge it back into `main`:

```bash
git checkout main
git merge new-feature
```

### Why branch instead of just editing `main` directly?

Because `main` should always be in a working state. If you're
mid-experiment and something breaks, you don't want that visible to everyone
pulling from `main`. Branches isolate risk.

## Working with a remote (e.g. GitHub)

A "remote" is a version of the repository hosted elsewhere (usually a
server). `origin` is the conventional name for your main remote.

```bash
git remote -v                # see configured remotes
git remote add origin <url>  # connect a local repo to a remote for the first time

git push origin main         # upload your commits
git pull origin main         # download and merge others' commits
git fetch origin              # download others' commits WITHOUT merging yet
```

**`pull` vs `fetch`**: `fetch` downloads the latest history so you can look
at it, but doesn't touch your working files. `pull` is `fetch` + `merge` in
one step — it actually updates your current branch.

## Merge conflicts

A conflict happens when Git can't automatically combine two changes — e.g.
you and a teammate both edited the same line of the same file differently.
Git will pause and mark the conflicting section in the file:

```
<<<<<<< HEAD
your version of the line
=======
their version of the line
>>>>>>> branch-name
```

To resolve: edit the file by hand to keep the version you want (delete the
`<<<<<<<`, `=======`, `>>>>>>>` markers), then:

```bash
git add the-conflicted-file.py
git commit
```

Conflicts are normal, not a sign you did something wrong — they just mean
Git needs a human decision.

## Undoing things

| Situation | Command |
|---|---|
| Unstage a file (keep the edit, remove from staging) | `git restore --staged file.py` |
| Discard uncommitted changes to a file | `git restore file.py` |
| Change the message of your last commit (not yet pushed) | `git commit --amend` |
| Undo the last commit but keep the changes in your working dir | `git reset --soft HEAD~1` |
| See what a specific past commit looked like | `git checkout <commit-hash> -- file.py` |

⚠️ `git reset --hard` and `git checkout .` **discard changes permanently** —
be careful with these, they don't go through the recycle bin.

## `.gitignore`

Some files shouldn't be tracked at all — secrets (`.env`), build artifacts,
dependency folders (`node_modules/`), OS files (`.DS_Store`). List patterns
in a `.gitignore` file at the repo root:

```
.env
node_modules/
__pycache__/
*.log
```

Anything matching a pattern in `.gitignore` is invisible to `git status`
and `git add .` — Git won't accidentally commit it. (This repo already has
one — see [.gitignore](../.gitignore).)

## Quick reference

```bash
git init                       # start a new repo
git clone <url>                # copy an existing repo
git status                     # what's changed
git add <file>                 # stage a file
git commit -m "message"        # save a snapshot
git push                       # upload to remote
git pull                       # download + merge from remote
git branch                     # list branches
git checkout -b <name>         # create + switch to a new branch
git merge <branch>             # merge a branch into the current one
git log --oneline              # view history
git diff                       # see unstaged changes
```

## What's next

Once this feels natural, the next layer worth learning is how a real team
uses Git day to day — pull requests, code review, and CI/CD pipelines that
run automatically on every push. That's covered in
[ci-cd/ci-cd-pipeline-explained.md](../ci-cd/ci-cd-pipeline-explained.md)
once it exists.
