"""
Standalone approval test — creates a pending request and waits for you to decide.

Run this, then go to Dashboard → Approval and click Approve or Reject.
Or check your email for one-click links.

Run:
  python test_approval.py
"""
import os
import sys
from dotenv import load_dotenv

from a2a_clients import ApprovalClient

load_dotenv()

ap = ApprovalClient(
    api_url=os.environ["A2A_API_URL"],
    token=os.environ["A2A_API_KEY"],
)

print("Creating a pending approval request...")
print("You have 2 minutes to Approve or Reject it.\n")

req = ap.request(
    action_type="issue_refund",
    description="Customer Jane Smith is requesting a $750.00 refund for order #ORD-9912 (product defect).",
    payload={
        "amount": 750.00,
        "customer_email": "jane.smith@example.com",
        "order_id": "ORD-9912",
        "reason": "Product arrived broken",
    },
    agent_name="approval-test",
    timeout_seconds=120,   # 2-minute window for this demo
)

print(f"Request ID: {req.request_id}")
print(f"Status:     {req.status}")
print()
print(">>> Go to Dashboard → Approval and click Approve or Reject")
print(">>> Or check your email for one-click links")
print()
print("Polling every 5 seconds...\n")

decision = ap.wait_for_decision(
    req.request_id,
    poll_interval_seconds=5,
    max_wait_seconds=120,
)

print(f"\nFinal decision: {decision.upper()}")
if decision == "approved":
    print("Refund would be processed now.")
elif decision == "rejected":
    print("Rejection email would be sent to customer.")
elif decision == "expired":
    print("No decision was made in time. Request expired.")
