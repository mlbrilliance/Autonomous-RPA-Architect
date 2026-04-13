# BW-19: StartTransaction Requires Robot Session Context

**Symptom:** Calling `POST /odata/Queues/UiPathODataSvc.StartTransaction`
with an external-application OAuth2 token (client_credentials grant)
always returns `204 No Content` — even when the queue has 160+ `New`
items visible via `GET /odata/QueueItems`.

Alternatively, if the wrapper key is wrong (`startTransactionParameters`
instead of `transactionData`), the response is `400 Bad Request:
"startTransactionParameters must not be null"`.

**Root cause:** The `StartTransaction` OData action leases a queue item
by binding it to the calling **robot's active job session**. When called
from an external application (which has no robot session), there's no
robot to bind to — so Orchestrator returns 204 ("nothing to lease") even
though items exist.

**Evidence:** Tested live on UiPath Community Cloud (April 2026):
- External app token + `transactionData: {Name: "MedicalClaims"}` → 204
- Same queue has 160 items with Status=New (verified via GET QueueItems)
- UiPath docs confirm StartTransaction is intended for robot-context use

**Workaround:** The Performer bypasses Orchestrator's queue transaction
entirely and reads directly from SuiteCRM. The flow:

1. Dispatcher pushes cases to the Orchestrator queue AND PATCHes the
   SuiteCRM case status to "Queued" (both happen).
2. Performer queries SuiteCRM for `filter[status][eq]=Queued` cases
   directly (not via StartTransaction).
3. After adjudication, Performer PATCHes the case to "Closed_Closed",
   "Rejected", or "Pending_Input" in SuiteCRM.
4. The Orchestrator queue becomes **tracking-only** — the real state
   of record lives in SuiteCRM.

This is less atomic than StartTransaction (two Performer instances
could process the same case) but works reliably with external-app auth
on Community Cloud's free tier. The single-robot-slot constraint (BW-14)
means only one Performer runs at a time anyway, so concurrency isn't
an issue in practice.

**Additional SuiteCRM filter gotcha:** ALL JSON:API filters require the
`[eq]` (or `[like]`) operator explicitly. `filter[name]=X` returns
`400: "Filter field name must be an array"`. Must use
`filter[name][eq]=X`. Additionally, URL brackets must be percent-encoded
(`%5B` / `%5D`) because .NET's HttpClient may handle raw brackets
differently across environments.
