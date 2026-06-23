"""Email service for admin notifications and invite delivery."""
from email.message import EmailMessage
from html import escape
import smtplib
from typing import Iterable, Tuple, Optional

from src.config import settings
from src.utils.logging import logger


def send_invite_email(recipient: str, invite_codes: Iterable[str]) -> Tuple[bool, Optional[str]]:
    """Send invite code email to a recipient.

    Returns:
        Tuple of (success, error_message)
    """
    host = settings.smtp_host.strip()
    user = settings.smtp_user.strip()
    password = settings.smtp_password
    from_addr = (settings.smtp_from or settings.smtp_user).strip()
    port = settings.smtp_port

    if not host or not user or not password or not from_addr:
        return False, "SMTP is not fully configured"

    codes = [code.strip() for code in invite_codes if code and code.strip()]
    if not codes:
        return False, "No invite codes provided"

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = recipient
    msg["Subject"] = "Your LogKeep Invite Code"

    codes_block = "\n".join(codes)
    plural = "code" if len(codes) == 1 else "codes"
    login_url = "https://logkeep.perdrizet.org/login"

    msg.set_content(
        f"Hello,\n\n"
        f"A LogKeep admin generated invite {plural} for you:\n\n"
        f"{codes_block}\n\n"
        f"Use this {plural} during registration on LogKeep.\n"
        f"Login/Register: {login_url}\n\n"
        f"LogKeep Admin\n"
    )

    escaped_codes = [escape(code) for code in codes]
    if len(escaped_codes) == 1:
        codes_html = (
            '<div style="background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 8px; '
            'padding: 12px 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, '
            'Liberation Mono, Courier New, monospace; font-size: 16px; color: #111827; letter-spacing: 0.3px;">'
            f"{escaped_codes[0]}"
            "</div>"
        )
    else:
        list_items = "".join(
            (
                '<li style="margin: 0 0 8px 0; list-style: none;">'
                '<span style="background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 6px; '
                'padding: 8px 10px; display: inline-block; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, '
                'Consolas, Liberation Mono, Courier New, monospace; font-size: 14px; color: #111827;">'
                f"{code}"
                "</span></li>"
            )
            for code in escaped_codes
        )
        codes_html = f'<ul style="padding: 0; margin: 0;">{list_items}</ul>'

    msg.add_alternative(
        f"""\
<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 24px; background: #f5f7fb; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color: #1f2937;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width: 620px; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden;">
          <tr>
            <td style="background: #2563eb; padding: 18px 24px; color: #ffffff; font-size: 20px; font-weight: 700;">
              LogKeep invitation
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 15px; line-height: 1.6;">
              <p style="margin: 0 0 14px 0;">Hello,</p>
              <p style="margin: 0 0 14px 0;">A LogKeep admin generated invite {plural} for you.</p>
              <p style="margin: 0 0 10px 0; font-weight: 600;">Your invite {plural}:</p>
              {codes_html}
              <p style="margin: 16px 0 0 0;">Use this {plural} during registration.</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 0 24px 24px 24px;">
              <a href="{login_url}" style="display: inline-block; background: #2563eb; color: #ffffff; text-decoration: none; font-weight: 600; padding: 10px 14px; border-radius: 8px;">
                Open LogKeep
              </a>
              <p style="margin: 12px 0 0 0; font-size: 13px; color: #6b7280;">
                If the button does not work, use this link: <a href="{login_url}" style="color: #2563eb;">{login_url}</a>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding: 14px 24px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280;">
              Sent by LogKeep Admin
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
""",
        subtype="html",
    )

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                # StartTLS is expected for port 587.
                if port in (587, 25):
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(msg)

        logger.info("Invite email sent to %s", recipient)
        return True, None

    except Exception as exc:
        logger.error("Failed to send invite email to %s: %s", recipient, exc)
        return False, "Failed to send invite email"
