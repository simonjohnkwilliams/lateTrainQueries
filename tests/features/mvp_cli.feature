Feature: MVP one-command claims for last week
  As Simon
  I want a single command that produces last week's claim files
  So that I do not need to set env vars or remember a long CLI for the MVP

  @offline
  Scenario: Default run covers last week of weekdays
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    When I run the MVP command
    Then the analysed dates are the 5 weekdays ending yesterday
    And claim files are written under "Results"

  @offline
  Scenario: days-back overrides the lookback length
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    When I run the MVP command with args --days-back 3
    Then the analysed dates are exactly 3 weekdays ending yesterday
    And claim files are written under "Results"

  @offline
  Scenario: Concrete from-date and to-date select an inclusive weekday range
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And credentials are discoverable at the default project path
    When I run the MVP command with args --from-date 2026-07-07 --to-date 2026-07-10
    Then the analysed dates are "2026-07-07,2026-07-08,2026-07-09,2026-07-10"
    And claim files are written under "Results"

  @offline
  Scenario: HSP_CREDENTIALS_FILE is optional when creds/trainConfig.txt exists
    Given today is "2026-07-15"
    And a stub HSP transport that returns no claimable services
    And HSP_CREDENTIALS_FILE is unset
    And credentials exist at "creds/trainConfig.txt" relative to the project
    When I run the MVP command
    Then the command exits successfully
    And claim files are written under "Results"
