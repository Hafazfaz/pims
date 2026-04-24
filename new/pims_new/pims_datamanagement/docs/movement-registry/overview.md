# Movement Registry - Overview

## Summary

The movement registry tracks file movements through the system. The following rules apply to all files managed by the registry.

## Rules

1. **Manual commit at end of movement** - Files must be manually committed when a movement registry entry is closed. This is not automatic.

2. **Version or file reference required** - Before closing, a file must either:
   - Reference a previous version of itself, or
   - Reference another related file

3. **No pending actions** - Before any movement is processed, the file must have zero pending actions. See [pending-actions.md](./pending-actions.md).

4. **File locking in transit** - Files are locked for the duration of transit. See [file-locking.md](./file-locking.md).

## Related

- [File Locking](./file-locking.md)
- [Pending Actions](./pending-actions.md)
- [Versioning](./versioning.md)
