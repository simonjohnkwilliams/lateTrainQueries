Feature: Reporting late trains between Godalming and London Waterloo
  As a Godalming-line commuter
  I want a CSV of the worst-delayed train each day
  So that I can see how reliable my commute has been

  Background:
    Given the HSP cache and Results directories are empty

  @offline
  Scenario: A train that arrives 23 minutes late is reported in the CSV
    Given the Darwin API returns one outbound service on "2020-01-01"
      And that service has the WAT arrival 23 minutes late
    When I run the late-train report for GOD to WAT
    Then the outbound CSV exists
      And the outbound CSV contains the row "2020-01-01,0727,23"

  @offline
  Scenario: An on-time train does not appear in the CSV
    Given the Darwin API returns one outbound service on "2020-01-02"
      And that service arrives at WAT exactly on time
    When I run the late-train report for GOD to WAT
    Then the outbound CSV exists
      And the outbound CSV contains no delay rows

  @offline
  Scenario: A train arriving 1 minute late is below the lateness threshold
    Given the Darwin API returns one outbound service on "2020-01-03"
      And that service arrives at WAT 1 minute late
    When I run the late-train report for GOD to WAT
    Then the outbound CSV exists
      And the outbound CSV contains no delay rows

  @offline
  Scenario: The worst-delayed train of the day is the one reported
    Given the Darwin API returns two outbound services on "2020-01-04"
      And one is 8 minutes late and the other is 41 minutes late
    When I run the late-train report for GOD to WAT
    Then the outbound CSV reports a delay of 41 minutes for "2020-01-04"

  @recorded
  Scenario: Replaying the recorded HSP responses from 2026-05-28
    # These fixtures were captured from the real hsp-prod.rockshore.net API
    # on 2026-05-28 (a quiet Thursday morning). Only the 07:07 ex-Havant
    # service was late enough at both GOD and WAT to clear the pipeline's
    # >1 minute threshold; it is the row that ends up in the CSV.
    Given the recorded GOD-WAT response set from "2026-05-28"
    When I run the late-train report for GOD to WAT against the recorded set
    Then the outbound CSV reports a delay of 3 minutes for "2026-05-28"
      And the departure time on that row is "0708"
