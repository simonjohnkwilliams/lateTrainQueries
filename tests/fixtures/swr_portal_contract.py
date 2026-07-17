"""Live SWR portal journey contract — selectors and labels from dry capture 2026-07-17.

These fixtures are **sanitized excerpts** (not full Angular bundles). Offline tests
assert the contract our Playwright wizard must honour so tests are not toys.
"""

# Step labels in the make-claim stepper
STEPPER_STEPS = (
    "Your details",
    "Journey",
    "Ticket",
    "Compensation",
    "Review",
)

LOGIN = {
    "url_path": "/en/login",
    "email": "input[type=email]",
    "password": "input[type=password]",
    "submit": "#submit-button",
    "submit_text": "Log in",
}

ACCOUNT = {
    "url_path": "/en/account",
    "heading": "Account Summary",
    "make_claim_path": "/en/make-claim",
}

JOURNEY = {
    "travel_date_role": ("textbox", "Travel date"),
    "from_role": ("combobox", "From"),
    "to_role": ("combobox", "To"),
    "leaving_at_aria": "Time: for example, 09:30 or 14:55",
    "find_journey": "#find-journey",
    "journey_card": "sr-journey-card",
    "delay_card": "mat-card.delay-duration-card",
    "delay_bands": (
        "Between 15 - 29 minutes",
        "Between 30 - 59 minutes",
        "Between 60 - 119 minutes",
        "120 minutes or more",
    ),
    "next_ticket_button": "Ticket",
}

TICKET = {
    "multi_question": "Are you claiming for more than one ticket?",
    "single_answer": "No",
    "paper_aria": "Select Paper as your ticket type",
    "eticket_aria": "Select E-ticket/M-ticket as your ticket type",
    "duration_return": "Return",
    "price_label": "Price",
    "ticket_number_label": "Ticket number, collection or booking reference",
    "ticket_number_rule": "5-digit number, collection or booking reference",
    "file_input": "input[type=file]",
    "confirm_button": "Confirm",
    "next_compensation_button": "Compensation",
}

REVIEW = {
    "next_from_compensation": "Review claim",
    "submit_button": "Submit claim",
    "recaptcha": "textarea[name=g-recaptcha-response]",
}
