"""
Thin HTTP clients for the three Midlantics A2A security modules.

These call the same backend endpoints that the dashboard uses.
No SDK install needed — just httpx + your API token (Supabase JWT).

How to get your token:
  Open the dashboard, open DevTools → Application → Local Storage →
  look for the key that starts with "sb-" → copy the access_token value.
  Or use the Supabase Python client to sign in and get a session token.
"""
from __future__ import annotations

import httpx
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyVerdict:
    verdict: str                        # "allow" | "flag" | "block"
    triggered_rules: list[dict]

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"

    @property
    def flagged(self) -> bool:
        return self.verdict == "flag"


@dataclass
class ScanVerdict:
    verdict: str                        # "clean" | "warn" | "block"
    threats: list[dict]
    clean: bool

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"


@dataclass
class ApprovalRequest:
    request_id: str
    status: str                         # "pending" | "approved" | "rejected" | "expired"
    created_at: str


class PolicyClient:
    """Call POST /policy/evaluate against your enabled policy rules."""

    def __init__(self, api_url: str, token: str) -> None:
        self._url = api_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def evaluate(
        self,
        action_type: str,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        agent_name: str | None = None,
    ) -> PolicyVerdict:
        """
        Evaluate an action against all enabled workspace policies.

        action_type:  a string label for the action, e.g. "send_email", "purchase", "delete_record"
        payload:      flat or nested dict of fields to match against rules
        """
        body: dict[str, Any] = {"action_type": action_type, "payload": payload or {}}
        if trace_id:
            body["trace_id"] = trace_id
        if agent_name:
            body["agent_name"] = agent_name

        resp = httpx.post(f"{self._url}/policy/evaluate", json=body, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        return PolicyVerdict(
            verdict=data["verdict"],
            triggered_rules=data.get("triggered_rules", []),
        )


class FirewallClient:
    """Call POST /firewall/scan to check content for threats."""

    def __init__(self, api_url: str, token: str) -> None:
        self._url = api_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def scan(
        self,
        content: str,
        context: str = "input",         # "input" | "output" | "tool_call"
        trace_id: str | None = None,
        agent_name: str | None = None,
    ) -> ScanVerdict:
        """
        Scan a string for: prompt injection, PII (SSN, CC, email, phone),
        jailbreak attempts, and data exfiltration patterns.

        context: where the content comes from — affects how it's logged.
        """
        body: dict[str, Any] = {"content": content, "context": context}
        if trace_id:
            body["trace_id"] = trace_id
        if agent_name:
            body["agent_name"] = agent_name

        resp = httpx.post(f"{self._url}/firewall/scan", json=body, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        return ScanVerdict(
            verdict=data["verdict"],
            threats=data.get("threats", []),
            clean=data.get("clean", True),
        )


class ApprovalClient:
    """
    Create and poll human-in-the-loop approval requests.

    Flow:
      1. agent calls request() → gets request_id, status="pending"
      2. reviewer gets an email with Approve/Reject buttons
         OR opens Dashboard → Approval and clicks there
      3. agent polls wait_for_decision() until status changes
    """

    def __init__(self, api_url: str, token: str) -> None:
        self._url = api_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def request(
        self,
        action_type: str,
        description: str,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        agent_name: str | None = None,
        timeout_seconds: int = 3600,
    ) -> ApprovalRequest:
        """
        Create a pending approval request.
        The reviewer will receive an email notification immediately.
        """
        body: dict[str, Any] = {
            "action_type": action_type,
            "description": description,
            "payload": payload or {},
            "timeout_seconds": timeout_seconds,
        }
        if trace_id:
            body["trace_id"] = trace_id
        if agent_name:
            body["agent_name"] = agent_name

        resp = httpx.post(f"{self._url}/approval/requests", json=body, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        return ApprovalRequest(
            request_id=data["request_id"],
            status=data["status"],
            created_at=data["created_at"],
        )

    def get_status(self, request_id: str) -> str:
        """Returns the current status: 'pending' | 'approved' | 'rejected' | 'expired'"""
        resp = httpx.get(
            f"{self._url}/approval/requests/{request_id}",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()["status"]

    def wait_for_decision(
        self,
        request_id: str,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 3600,
    ) -> str:
        """
        Block until approved/rejected/expired, polling every poll_interval_seconds.
        Returns the final status string.
        """
        import time
        waited = 0
        while waited < max_wait_seconds:
            status = self.get_status(request_id)
            if status != "pending":
                return status
            print(f"  [approval] waiting... status={status} ({waited}s elapsed)")
            time.sleep(poll_interval_seconds)
            waited += poll_interval_seconds
        return "expired"
