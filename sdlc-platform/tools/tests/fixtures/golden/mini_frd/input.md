# Functional Requirements Document: Team Leave Tracker

## 1. Purpose
The Team Leave Tracker lets employees request leave and lets team leads approve it.

## 2. Functional requirements
- REQ-001 The system shall let an employee submit a leave request for a date range.
- REQ-002 The system shall let the team lead approve or reject a pending request with a comment.
- REQ-003 The system shall reject a request that overlaps an existing approved request.
- REQ-004 An employee may have at most 25 days of annual leave per calendar year.

## 3. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR-001 | Pages load within 2 seconds for 50 concurrent users. |
| NFR-002 | All traffic uses HTTPS. |

## 4. Out of scope
Payroll processing is out of scope.
