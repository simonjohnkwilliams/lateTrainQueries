Feature: End-to-end claim pipeline (GOD <-> WAT)
  As Simon
  I want one command that turns a week of HSP data into file-ready claims
  So that filing is copying verified rows into the SWR form

  @offline
  Scenario: A claimable week produces CSV and JSON claim files
    Given a stubbed week with a 25-minute-late outbound on "2026-05-28"
    When I run the claim pipeline for that week
    Then a CSV and a JSON claim file are written
    And the output contains a claim for "2026-05-28"

  @offline
  Scenario: A day that failed to fetch is reported as not analysed
    Given a stubbed week where "2026-05-28" fails to fetch
    When I run the claim pipeline for that week
    Then the day "2026-05-28" is reported as not analysed
    And it is not counted as a clean no-claim day

  @recorded
  Scenario: The recorded quiet Thursday is analysed with no claims
    Given the recorded GOD-WAT fixtures from "2026-05-28"
    When I run the claim pipeline for that day
    Then the day "2026-05-28" is analysed with zero claims
    And a CSV and a JSON claim file are written
