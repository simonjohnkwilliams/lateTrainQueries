# Characterised from live Gmail export PDFs for claim SWR-0218-108-579
# (2026-07-17…18). Used by offline FR38 matcher tests.

from __future__ import annotations

CLAIM_ID = "SWR-0218-108-579"
FROM_ADDR = "No-replySWRDR@firstcustomercontact.com"

RECEIVED = {
    "subject": f"South Western Railway Delay Repay - Claim {CLAIM_ID} - RECEIVED",
    "from_addr": FROM_ADDR,
    "sent": "2026-07-17T15:33:00",
    "body": f"""Dear Simon John Williams,
Thank you for submitting your delay repay claim to South Western Railway. Your claim
reference is {CLAIM_ID} - you will need to use this reference in any
communications regarding this claim.
We will respond to your claim within 20 working days, but you can check the status of
your claim at any time by using our online web page at https://delayrepay.
southwesternrailway.com/claim/{CLAIM_ID}
If your claim is approved for the delay you have entered, you can expect to receive
compensation of £1.57.
A summary of the details you submitted is shown below for your records:
Claim Reference: {CLAIM_ID}
Travel Date: Thu, 16 Jul 2026
Departing: 09:41 from GODALMING to LONDON WATERLOO
Delay: between 15 - 29 minutes
Compensation Method: BACS
Yours sincerely,
Customer Support Team
""",
}

APPROVED = {
    "subject": f"South Western Railway Delay Repay - Claim {CLAIM_ID} - Approved",
    "from_addr": FROM_ADDR,
    "sent": "2026-07-18T09:02:00",
    "body": f"""Dear Simon John Williams,
Thank you for your delay repay claim which we received on Fri, 17 Jul 2026. We are
sorry that you experienced a delay to your journey.
Your claim has been checked using a set process and the details of any delay verified
using industry systems holding historic train running information. We have reviewed
your claim and can confirm the following:
Travel Date: Thu, 16 Jul 2026
Departing: 09:41 from GODALMING to LONDON WATERLOO
Decision: Approved
We have confirmed that the delay you experienced was between 15 - 29 minutes and
that you are entitled to £1.57 in compensation. For further information on how we have
calculated your award amount, please visit the Delay Repay page on the South
Western Railway website.
If you believe we've made the wrong decision or that you've given us the wrong
information, then the quickest way to update us is to appeal the claim using our online
web page at https://delayrepay.southwesternrailway.com/claim/{CLAIM_ID}
before Fri, 14 Aug 2026.
Yours sincerely,
Customer Support Team
""",
}

PAYMENT_SENT = {
    "subject": f"South Western Railway Delay Repay - Claim {CLAIM_ID} - PAYMENT SENT",
    "from_addr": FROM_ADDR,
    "sent": "2026-07-18T13:01:00",
    "body": f"""Dear Simon John Williams,
Thank you for your delay repay claim which we received on Fri, 17 Jul 2026.
A payment of £1.57 is now on its way to you via BACS. The payment should appear in
your account within 5-10 working days.
Yours sincerely,
Customer Support Team
""",
}

ALL_STAGES = (RECEIVED, APPROVED, PAYMENT_SENT)
