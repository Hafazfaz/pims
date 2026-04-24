# Pending Actions

## Overview

Before a file can be moved or committed in the movement registry, it must be verified that there are no pending actions against it.

## Rules

- A pending action check must be performed before any movement is initiated
- If pending actions exist, the movement must be blocked and an error returned
- The file cannot be locked for transit until it is clear of pending actions

## What Counts as a Pending Action

- Unresolved approvals
- Open edits not yet saved or committed
- Active workflows referencing the file
- Unacknowledged notifications tied to the file

## Verification

Before initiating a movement:

1. Query all pending actions for the file
2. If count > 0, reject the movement and surface the pending actions to the user
3. If count == 0, proceed with locking and transit

## Related

- [Overview](./overview.md)
- [File Locking](./file-locking.md)
