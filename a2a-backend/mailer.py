"""Resend email client — thin wrapper around the Resend REST API."""
from __future__ import annotations

import os
import httpx

_RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
_FROM = os.getenv("EMAIL_FROM", "Midlantics A2A <notifications@a2a.midlantics.com>")


async def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Returns True on success, False on failure."""
    if not _RESEND_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {_RESEND_API_KEY}"},
                json={"from": _FROM, "to": [to], "subject": subject, "html": html},
            )
            return res.status_code == 200
    except Exception:
        return False


def approval_email_html(
    *,
    action_type: str,
    description: str,
    agent_name: str | None,
    approve_url: str,
    reject_url: str,
    dashboard_url: str,
) -> str:
    agent_line = f"<p style='color:#94a3b8;margin:0 0 4px'>Agent: <strong style='color:#e2e8f0'>{agent_name}</strong></p>" if agent_name else ""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:32px 16px">
  <div style="max-width:480px;margin:0 auto">
    <div style="margin-bottom:24px">
      <span style="font-size:18px;font-weight:700;color:#fff">Midlantics</span>
      <span style="font-size:18px;font-weight:700;color:#818cf8"> A2A</span>
    </div>

    <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;margin-bottom:16px">
      <p style="color:#94a3b8;font-size:13px;margin:0 0 16px;text-transform:uppercase;letter-spacing:.05em">Approval required</p>
      <h2 style="color:#fff;font-size:20px;margin:0 0 8px">{action_type}</h2>
      <p style="color:#cbd5e1;margin:0 0 16px;line-height:1.6">{description}</p>
      {agent_line}
    </div>

    <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
      <tr>
        <td style="padding-right:8px;width:50%">
          <a href="{approve_url}"
             style="display:block;text-align:center;background:#16a34a;color:#fff;font-weight:600;font-size:15px;padding:14px;border-radius:10px;text-decoration:none">
            ✓ Approve
          </a>
        </td>
        <td style="padding-left:8px;width:50%">
          <a href="{reject_url}"
             style="display:block;text-align:center;background:#b91c1c;color:#fff;font-weight:600;font-size:15px;padding:14px;border-radius:10px;text-decoration:none">
            ✗ Reject
          </a>
        </td>
      </tr>
    </table>

    <p style="text-align:center;margin:0">
      <a href="{dashboard_url}" style="color:#6366f1;font-size:13px;text-decoration:none">
        Open full dashboard →
      </a>
    </p>

    <p style="color:#475569;font-size:12px;margin:24px 0 0;text-align:center;line-height:1.5">
      This link expires when the request times out.<br>
      You received this because you are a reviewer in this workspace.
    </p>
  </div>
</body>
</html>"""
