# Document Management — Workflow Map

This document extracts the workflow state machine and maps it to the app (DB fields, API contracts, UI hints). It is based on the provided PDF and on existing app behavior. Where the PDF is ambiguous I note reasonable assumptions; we can refine after you confirm.

## 1) Core workflow states

- submitted — file has been created/submitted by staff and is waiting for the assigned receiver (HOD/Dept) to pick up.
- acknowledged — the receiver has acknowledged receipt (optional step depending on process).
- pending — under review/processing by HOD (awaiting approval/rejection or routing).
- approved — HOD accepted the file and allowed onward processing (may generate next workflow row or close).
- rejected — HOD rejected the file; typically must be returned to originator with comments.
- escalated — flagged for higher-level intervention (Admin or Director).
- archived/closed — final completed state (no further actions expected).

Notes: the repo already uses `submitted`, `pending`, `approved`, `rejected` in multiple places; this map extends those slightly with `acknowledged`, `escalated`, and `archived` which are common in DMS workflows.

## 2) Allowed transitions (role-enforced)

Each transition lists who may perform it and whether a comment is required.

- submitted -> acknowledged
  - Who: receiver (HOD/department) or system (auto)
  - Comment: optional

- acknowledged -> pending
  - Who: receiver/HOD
  - Comment: optional

- pending -> approved
  - Who: HOD (or Admin override)
  - Comment: optional, but recommended

- pending -> rejected
  - Who: HOD
  - Comment: REQUIRED (reason for rejection; UI must require comment)

- any -> escalated
  - Who: HOD or Admin
  - Comment: REQUIRED (reason for escalation)

- approved -> archived
  - Who: HOD or system scheduled job
  - Comment: optional

- rejected -> submitted (resubmit)
  - Who: Originator (staff) after addressing comments
  - Comment: optional (reason for changes)

Invalid transitions should be rejected by the server with a clear per-item error.

## 3) Roles & permissions

- Staff (submitter)
  - Create files/workflows, view own files, resubmit after rejection.
- HOD (receiver/approver)
  - Acknowledge, move to pending, Approve, Reject (with required comment), Escalate.
- Admin / Director
  - Override (force approve/reject or escalate), view all workflows.

Server-side permission checks MUST be performed for each update operation; client-only checks are insufficient.

## 4) Database mapping (suggested fields)

Table: `workflows` (existing schema may differ; these are recommended columns)

- id (INT PK)
- file_id (INT FK -> files.id)
- sender_id (INT -> users.id)
- receiver_id (INT -> users.id) — optional; department/HOD
- status (VARCHAR) — current state; enum of the states above
- comment (TEXT) — optional latest comment for status change
- created_at (DATETIME)
- updated_at (DATETIME)
- due_date (DATE/TIMESTAMP) — optional SLA
- acknowledged_at (DATETIME) — optional
- history_json / or separate `file_history` table — recommended to keep immutable history records

If you already have a `file_history` table (recommended) every state change should insert a history row with actor_id, from_status, to_status, comment, timestamp.

## 5) API contracts (single and bulk)

Single workflow update (existing):

PUT /api/workflows/:workflow_id
Request JSON:
{
  "status": "approved" | "rejected" | "pending" | "escalated" | ...,
  "comment": "Optional or required depending on transition"
}

Responses:
- 200 OK — success; body: {"ok":true, "workflow_id": <id>, "new_status":"approved"}
- 400 Bad Request — invalid payload
- 403 Forbidden — actor not allowed to perform transition
- 422 Unprocessable Entity — invalid transition (e.g., approved -> submitted)
- 404 Not Found — workflow id not found

Bulk workflow update (existing):

PUT /api/workflows/bulk
Request JSON:
{
  "workflow_ids": [123, 456, ...],
  "status": "approved",
  "comment": "Optional or required depending on transition"
}

Response (recommended shape):
HTTP 207 Multi-Status (or 200 with structured body)
{
  "updated": [123, 456],
  "errors": [
    {"workflow_id": 789, "error": "forbidden: not receiver"},
    {"workflow_id": 321, "error": "invalid transition: approved <- archived"}
  ]
}

Server should attempt each item independently, apply per-item permission & transition validation, update allowed ones and return the per-item result. This allows clients to present a summary and retry failed items.

## 6) UI guidance (Hod/hod.js)

- Show only allowed action buttons per-row based on current `status` and user's role. Example:
  - if status === 'pending' and user.role === 'hod' -> show Approve, Reject, Escalate buttons
  - if status === 'submitted' -> show Acknowledge (if role is receiver)

- For actions that require comments (Reject, Escalate), open a modal to collect the comment and then call the API.

- Bulk actions: only enable bulk action buttons for rows where the same transition is allowed. If mixed (some selected rows cannot be moved to the requested state), either disable bulk button or warn and show per-item report after the request.

## 7) Server-side validation pseudo-code

function canTransition(actor, currentStatus, requestedStatus, workflow){
  // check permissions
  if(requestedStatus === 'approved' && !actor.isHod && !actor.isAdmin) return {ok:false, error:'forbidden'};
  // check allowed transitions mapping
  const allowed = transitions[currentStatus] || [];
  if(!allowed.includes(requestedStatus)) return {ok:false, error:'invalid transition'};
  // comment requirement
  if((requestedStatus === 'rejected' || requestedStatus === 'escalated') && !payload.comment) return {ok:false, error:'comment required'};
  return {ok:true};
}

For each update (single or bulk) run canTransition(), if ok perform DB update and insert history row; otherwise, return per-item error.

## 8) Edge cases and recommendations

- Race conditions: two approvers attempting different transitions simultaneously — use DB row locking or optimistic concurrency (updated_at check) to prevent lost updates.
- Long-running/async transitions: Escalate might open a ticket — consider decoupling by emitting an event or queue job.
- Bulk updates: limit the maximum count per request (e.g., 200) to avoid timeouts.
- Auditing: always persist an immutable history for compliance.

## 9) Next concrete changes I will implement (if you confirm)

1. Add server-side transition validation to `backend/app.py` (PUT single & PUT bulk) following the `canTransition` rules.
2. Ensure every successful transition inserts a `file_history` row with actor, from, to, comment, timestamp.
3. Update `Hod/hod.js` to show allowed actions and require comments where necessary; add per-item error reporting UI for bulk.

---

If any of the inferred states or rules above differ from the PDF's specifics, tell me which ones to change and I will update the map and implement the backend accordingly.
