"""
One-time setup: creates the two policies that the agent demo depends on.

Run this once before running agent.py:
  python setup_policies.py

After running, go to Dashboard → Policy Engine to see them.
You can edit them there too.
"""
from __future__ import annotations

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL   = os.environ["A2A_API_URL"]
API_TOKEN = os.environ["A2A_API_KEY"]

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}


def create_policy(name: str, description: str, rules: list[dict]) -> str:
    resp = httpx.post(
        f"{API_URL}/policy/policies",
        json={"name": name, "description": description, "enabled": True, "rules": rules},
        headers=headers,
    )
    if resp.status_code == 402:
        print(f"  ERROR: Policy Engine requires a paid plan. Upgrade at Dashboard → Billing.")
        return ""
    resp.raise_for_status()
    policy_id = resp.json()["id"]
    print(f"  Created: {name} (id={policy_id})")
    return policy_id


if __name__ == "__main__":
    print("Setting up policies...\n")

    # Policy 1: Block emails to competitor domains
    # Match condition:  action_type = "send_email"  AND  to_address matches the regex
    create_policy(
        name="Block competitor domains",
        description="Prevent the agent from emailing known competitor addresses",
        rules=[
            {
                "name": "Block @competitor.com",
                "description": "Never email competitor.com",
                "match": {
                    "action_type": "send_email",
                    "to_address": r".*@competitor\.com",
                },
                "action": "block",
                "severity": "critical",
            },
            {
                "name": "Block @rival.io",
                "description": "Never email rival.io",
                "match": {
                    "action_type": "send_email",
                    "to_address": r".*@rival\.io",
                },
                "action": "block",
                "severity": "critical",
            },
        ],
    )

    # Policy 2: Flag large refund requests (doesn't block, just logs a flag)
    # The agent has its own approval gate for >$500, but this also flags it
    # in the Policy Engine evaluation log for audit purposes.
    create_policy(
        name="Flag large refunds",
        description="Flag refund requests above $500 for review",
        rules=[
            {
                "name": "Large refund flag",
                "description": "Refunds over $500 are flagged",
                "match": {
                    "action_type": "send_email",
                    "refund_amount_gt": 500,       # _gt suffix = numeric greater-than
                },
                "action": "flag",
                "severity": "high",
            },
        ],
    )

    # Policy 3: Block suspicious action types entirely
    create_policy(
        name="Block dangerous actions",
        description="Prevent the agent from taking destructive actions",
        rules=[
            {
                "name": "Block delete operations",
                "description": "Never allow delete actions",
                "match": {
                    "action_type": "delete_record",
                },
                "action": "block",
                "severity": "critical",
            },
            {
                "name": "Block bulk export",
                "description": "Flag attempts to export large amounts of data",
                "match": {
                    "action_type": "export_data",
                },
                "action": "flag",
                "severity": "high",
            },
        ],
    )

    print("\nDone. Visit Dashboard → Policy Engine to see and edit your policies.")
    print("Then run:  python agent.py")
