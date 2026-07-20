"""Gmail adapter package — OAuth + API client for Epic 7 ops email."""
from trainline.adapters.gmail.auth import (
    GMAIL_SCOPES,
    GmailConfig,
    get_credentials,
    run_auth_flow,
    store_credentials,
)
from trainline.adapters.gmail.claim_mail import (
    ClaimMailStage,
    SwrClaimMail,
    parse_gmail_message,
    parse_swr_claim_mail,
    swr_claim_search_query,
)
from trainline.adapters.gmail.client import GmailClient
from trainline.adapters.gmail.errors import GmailAuthError, GmailError
from trainline.adapters.gmail.ticket_mail import (
    build_ticket_mail_query,
    extract_image_attachments,
)

__all__ = [
    "ClaimMailStage",
    "GMAIL_SCOPES",
    "GmailAuthError",
    "GmailClient",
    "GmailConfig",
    "GmailError",
    "SwrClaimMail",
    "build_ticket_mail_query",
    "extract_image_attachments",
    "get_credentials",
    "parse_gmail_message",
    "parse_swr_claim_mail",
    "run_auth_flow",
    "store_credentials",
    "swr_claim_search_query",
]
