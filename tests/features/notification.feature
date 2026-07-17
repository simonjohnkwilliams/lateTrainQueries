Feature: Notification adapter + email config
  As Simon
  I want email settings loaded from env and an injectable SMTP seam
  So that digest credentials stay out of the repo and offline tests need no network

  @offline
  Scenario: Missing SMTP settings name every required key
    Given no email environment variables are set
    When email config is loaded
    Then an email config error names "SMTP_HOST,SMTP_PORT,SMTP_USER,SMTP_PASSWORD,DIGEST_TO"

  @offline
  Scenario: Partial missing settings list only absent keys
    Given email environment variables are set except "SMTP_PASSWORD,DIGEST_TO"
    When email config is loaded
    Then an email config error names "SMTP_PASSWORD,DIGEST_TO"
    And the email config error does not name "SMTP_HOST"

  @offline
  Scenario: Notification adapter is importable without other adapters
    When the notification adapter module is imported
    Then it does not import hsp_client, storage, config, or claim_submission

  @offline
  Scenario: Digest lists claimable rows
    Given day results with one claimable outbound claim
    When the digest is rendered
    Then the digest text includes "2026-07-10" "outbound" "15-29" "GOD" "WAT" "20"

  @offline
  Scenario: Fetch-failed days appear as not analysed
    Given day results with a fetch-failed day and a clean no-claim day
    When the digest is rendered
    Then the digest marks "2026-07-09" as not analysed
    And the digest does not mark "2026-07-08" as not analysed

  @offline
  Scenario: Zero claimable rows stated explicitly
    Given day results with only clean no-claim days
    When the digest is rendered
    Then the digest text says no claimable rows were found
