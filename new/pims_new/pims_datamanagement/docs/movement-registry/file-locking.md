# File Locking

## Overview

Files must be locked for the entire duration of their transit within the movement registry. This prevents concurrent modifications or conflicting operations.

## Rules

- A file is locked as soon as a movement begins
- The lock is held until the movement is fully committed or cancelled
- No other process may modify a locked file
- Attempting to act on a locked file must return an error

## Lock States

| State | Description |
|-------|-------------|
| `unlocked` | File is free to be acted upon |
| `locked_in_transit` | File is currently in a movement and cannot be modified |

## Related

- [Overview](./overview.md)
- [Pending Actions](./pending-actions.md)
