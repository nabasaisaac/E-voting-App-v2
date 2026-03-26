# E-voting-App-v2

---

## Changes made (backend fixes)

This section summarizes backend changes and where they were made.

### Elections (`evoting-app-backend/elections/`)

- **`evoting-app-backend/elections/serializers.py`**
  - **Validation off-by-one fixes**
    - `VotingStationCreateSerializer.validate_capacity`: capacity must be \(\ge 1\)
    - `PositionCreateSerializer.validate_max_winners`: max_winners must be \(\ge 1\)
  - **Candidate age validation consistency**
    - `CandidateCreateSerializer.validate_date_of_birth`: month/day-aware age calculation
  - **Poll creation hardening (`PollCreateSerializer`)**
    - rejects **duplicate IDs** in `position_ids` and `station_ids`
    - adds basic **max-size guards** for those lists
    - validates positions are **active** (`is_active=True`)
    - rejects **overlapping** draft/open polls for the same stations and date range

- **`evoting-app-backend/elections/services.py`**
  - **Query correctness**
    - `CandidateService.search` now stays a **QuerySet** (no list conversion), preserving pagination/ordering.
  - **Input sanitization**
    - `min_age` / `max_age` now validate as integers and raise DRF `ValidationError` if invalid.
  - **Exception consistency**
    - Poll business-rule failures now raise DRF `ValidationError` (not `ValueError`).
  - **Audit correctness**
    - Fixed open vs reopen logging to use the **previous** poll status.

- **`evoting-app-backend/elections/views.py`**
  - Removed now-unnecessary `ValueError`?400 catch blocks (services now raise DRF `ValidationError` directly).

### Voting (`evoting-app-backend/voting/`)

- **`evoting-app-backend/voting/serializers.py`**
  - `CastVoteSerializer.validate_votes` now enforces: each vote item must either **select a candidate** or **abstain** (cannot be neither; cannot be both).

- **`evoting-app-backend/voting/views.py`**
  - `CastVoteView` now returns:
    - **404** when the poll does not exist
    - **400** with DRF validation details when vote casting fails via `ValidationError`

### Accounts (`evoting-app-backend/accounts/`)

- **`evoting-app-backend/accounts/services.py`**
  - **Mistake**: registration failures were not audited (e.g., invalid/inactive `station_id` caused a rejection but left no audit trail).
  - **Fix**: when registration fails due to an invalid/inactive station, the service now logs `REGISTER_FAILED` with the reason before raising DRF `ValidationError`.

### Audit (`evoting-app-backend/audit/`)

- **`evoting-app-backend/audit/services.py`**
  - **Mistake**: `get_recent()` returned arbitrary/oldest logs because it didn?t order by timestamp.
  - **Fix**: `get_recent()` now orders by `-timestamp` so the newest audit entries are returned first.

### Voting services (`evoting-app-backend/voting/`)

- **`evoting-app-backend/voting/services.py`**
  - **Mistake**: business-rule failures used `ValueError`, service trusted the view to enforce verification, and failed vote attempts were not logged.
  - **Fix**:
    - raises DRF `ValidationError` for business-rule failures (consistent API errors)
    - enforces `is_verified` and `is_active` inside the service (defensive)
    - blocks repeat voting attempts per poll (application-level check)
    - logs `VOTE_FAILED` audit entries on validation failures
    - reduces N+1 queries by bulk-fetching poll positions for the submitted votes
