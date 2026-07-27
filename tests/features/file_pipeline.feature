Feature: Single-command assess → gate → file pipeline
  As Simon
  I want one --file command that assesses, gates tickets, files claims, and audits
  So that weekly Delay Repay is fully hands-off offline

  @offline
  Scenario: --file with matching ticket files via fake browser
    Given today is "2026-07-15"
    And a stubbed week with a 25-minute-late outbound on "2026-07-10"
    And credentials are discoverable at the default project path
    And ready_to_claim has a ticket for "2026-07-10"
    And a recording fake browser is installed
    And valid SMTP environment variables are set
    And a recording digest transport is installed
    When I run the MVP command with args --file --digest --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits successfully
    And claim files are written under "Results"
    And the filing audit has one success line
    And the ticket moved to claimed
    And one digest email was sent

  @offline
  Scenario: --file blocks submit when tickets are missing
    Given today is "2026-07-15"
    And a stubbed week with a 25-minute-late outbound on "2026-07-10"
    And credentials are discoverable at the default project path
    And ready_to_claim is empty
    And a recording fake browser is installed
    When I run the MVP command with args --file --strict-all-tickets --from-date 2026-07-10 --to-date 2026-07-10
    Then the command exits with a non-zero status
    And claim files are written under "Results"
    And no filing audit was written
    And the fake browser was not used
