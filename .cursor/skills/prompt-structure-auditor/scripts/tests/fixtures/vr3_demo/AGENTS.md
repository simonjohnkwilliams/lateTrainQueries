# Finance Tracker - Agent Context

This document records setup steps and decisions so we don't repeat work.

## Current Focus: CSV Import
Primary flow is now CSV upload for bank transactions.

## CSV Format
- Headers: Date, Description, Money In, Money Out
- Date: DD/MM/YYYY

## TrueLayer (On Hold – Can Return)
TrueLayer integration is implemented but de-prioritised.

## Decision: Try Live Environment
Debugging notes for later.

## Debugging invalid client_id
Sandbox continues to return invalid client_id.

## Known Issue: Sandbox invalid client_id
Despite correct setup, sandbox auth fails.

## TrueLayer Setup
### Console Configuration
- Redirect URI: http://localhost:8080/oauth2/callback
- Copy client_id and client_secret

### Config changes for Live
- Redirect URI: http://localhost:8080/oauth2/callback
- Copy client_id and client_secret

### Live Console checklist
- Add redirect URI: http://localhost:8080/oauth2/callback
- Copy client_id and client_secret
