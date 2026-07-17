Feature: Ticket artifact gate
  As Simon
  I want ticket files named and matched to claim dates
  So that filing never proceeds without proof

  @offline
  Scenario: Scan accepts valid names and rejects misnamed
    Given a ticket directory with files "07-10-ABC123.pdf,ticket.pdf,2026-07-10.jpg"
    When the ticket directory is scanned
    Then one valid ticket is found for "07-10"
    And invalid files include "ticket.pdf" and "2026-07-10.jpg"
    And each invalid reason mentions the expected format

  @offline
  Scenario: Matcher reports missing claim dates
    Given claims for dates "2026-07-08,2026-07-09,2026-07-10"
    And valid tickets for "07-08,07-10"
    When tickets are matched to claims
    Then matching fails
    And missing dates include "2026-07-09"
    And the mapping covers "2026-07-08,2026-07-10"

  @offline
  Scenario: --check-tickets fails with human-readable gaps
    Given claims JSON with dates "2026-07-08,2026-07-10"
    And a ticket directory with files "07-08-A.pdf"
    When I run --check-tickets against that output
    Then the command exits with a non-zero status
    And stderr mentions missing date "2026-07-10"

  @offline
  Scenario: --check-tickets succeeds when all dates covered
    Given claims JSON with dates "2026-07-10"
    And a ticket directory with files "07-10-ABC123.pdf"
    When I run --check-tickets against that output
    Then the command exits successfully

  @offline
  Scenario: --check-tickets reports misnamed files via CLI
    Given claims JSON with dates "2026-07-10"
    And a ticket directory with files "ticket.pdf"
    When I run --check-tickets against that output
    Then the command exits with a non-zero status
    And stderr mentions missing date "2026-07-10"
    And stderr mentions misnamed file "ticket.pdf"
