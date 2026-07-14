Feature: Live end-to-end run against the real Darwin HSP API
  This scenario is opt-in. It is skipped unless HSP_CREDENTIALS_FILE is set and
  the file contains valid Open Rail Data credentials. The CI pipeline can run
  it by setting that variable on a secret.

  @live
  Scenario: A real GOD -> WAT request produces a Results CSV
    Given HSP credentials are available via the HSP_CREDENTIALS_FILE env var
    When I run the late-train pipeline for a single weekday window of GOD to WAT
    Then a serviceMetrics JSON file is written for that day
      And a serviceDetails JSON file is written for at least one service
      And the outbound CSV header line is written
