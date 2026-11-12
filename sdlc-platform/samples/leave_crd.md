# Acme Corp: Leave Management System, Client Requirements

## 1. Background

Acme Corp has about 400 employees in two offices (Bengaluru and Pune). Leave is currently tracked in spreadsheets maintained by HR, and requests are made over email. This causes errors in leave balances, slow approvals, and no visibility of who is on leave.

We want a web-based Leave Management System that employees, managers and HR can use.

## 2. Goals

- Reduce leave approval turnaround to under 2 working days.
- Remove manual balance tracking by HR.
- Give managers visibility of team availability.

## 3. Users

- Employees apply for leave and see their balances.
- Reporting managers approve or reject leave requests from their team.
- HR administrators manage leave policies, holidays and employee records.

## 4. Requirements

### 4.1 Login

All users must log in with their company email and password. Users should only see the functions for their role.

### 4.2 Employee records

HR must be able to add and update employees with name, email, department, reporting manager, joining date and employment type. Employee data is personal data and must only be visible to HR and the employee's manager.

### 4.3 Leave types

The company has Casual Leave (12 days per year), Sick Leave (10 days per year), Earned Leave (15 days per year) and Unpaid Leave. HR should be able to add new leave types later.

Sick leave of more than 2 consecutive days needs a medical certificate.

### 4.4 Applying for leave

- Employees apply for leave by selecting the leave type, start date, end date and a reason.
- Half-day leave should be possible.
- The system must not allow leave that exceeds the available balance, except Unpaid Leave.
- Weekends and company holidays must not be counted as leave days.
- Employees must not be able to apply for overlapping leave.

### 4.5 Approval

The reporting manager approves or rejects the request with a comment. If the manager does not act quickly, the request should go to HR. When a request is approved, the balance is reduced.

Employees can cancel a request that is still pending. Cancelling approved leave should be possible before the leave starts.

### 4.6 Notifications

Employees and managers should get an email when leave is applied, approved, rejected or cancelled.

### 4.7 Balances and year end

Leave is credited at the start of the year. Earned leave can be carried forward to next year up to a limit. New joiners get leave on a pro-rata basis.

### 4.8 Reports

HR wants a report of leave taken per employee and department, exportable to Excel. Managers want a calendar showing who in the team is on leave.

### 4.9 Payroll

Unpaid leave days must be shared with the payroll team every month.

## 5. Other expectations

- The system should be fast and easy to use.
- It should be available during office hours.
- All approvals and balance changes must be auditable.

## 6. Out of scope

Attendance tracking and timesheets are not part of this project.
