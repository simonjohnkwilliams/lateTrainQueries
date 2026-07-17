Feature: CLI weekly digest integration
  As Simon
  I want the digest sent after a successful assess run when requested
  So that I get a weekly nudge without a separate command

  @offline
  Scenario: --digest sends email after assess via fake transport
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    And valid SMTP environment variables are set
    And a recording digest transport is installed
    When I run the MVP command with args --digest --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits successfully
    And claim files are written under "Results"
    And one digest email was sent
    And the digest subject mentions claimable rows or none

  @offline
  Scenario: Default run does not send digest
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    And a recording digest transport is installed
    When I run the MVP command with args --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits successfully
    And no digest email was sent

  @offline
  Scenario: SMTP failure is best-effort unless --digest-strict
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    And valid SMTP environment variables are set
    And a failing digest transport is installed
    When I run the MVP command with args --digest --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits successfully
    And claim files are written under "Results"

  @offline
  Scenario: --digest-strict fails the run on SMTP error
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    And valid SMTP environment variables are set
    And a failing digest transport is installed
    When I run the MVP command with args --digest --digest-strict --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits with a non-zero status
    And claim files are written under "Results"

  @offline
  Scenario: --digest without SMTP config names missing keys
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    And no email environment variables are set
    When I run the MVP command with args --digest --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits with a non-zero status
    And stderr names missing SMTP keys
