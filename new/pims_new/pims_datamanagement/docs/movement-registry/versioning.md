# Versioning

## Overview

At the end of a movement registry entry, a file must be manually committed. As part of that commit, the file must include a reference — either to a previous version of itself or to another related file.

## Rules

- Manual commit is required to close a movement registry entry — this does not happen automatically
- The commit must include one of the following:
  - A reference to a **previous version** of the same file
  - A reference to **another file** in the registry

## Why This Is Required

This ensures full traceability. Every file in the registry can be traced back through its history or linked to related files, preventing orphaned or untracked entries.

## Commit Checklist

Before committing at end of movement:

- [ ] Pending actions cleared (see [pending-actions.md](./pending-actions.md))
- [ ] File lock released after transit (see [file-locking.md](./file-locking.md))
- [ ] Previous version reference OR related file reference added
- [ ] Manual commit performed

## Related

- [Overview](./overview.md)
- [File Locking](./file-locking.md)
- [Pending Actions](./pending-actions.md)
