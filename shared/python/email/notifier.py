"""Email notification module for failure alerts."""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Email notifier for sending failure alerts.

    Supports SMTP (Gmail compatible) for sending notifications
    when pipeline failures occur.
    """

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        notification_email: str | None = None,
    ):
        """
        Initialize the email notifier.

        Args:
            smtp_host: SMTP server host (defaults to env var)
            smtp_port: SMTP server port (defaults to env var)
            smtp_user: SMTP username (defaults to env var)
            smtp_password: SMTP password (defaults to env var)
            notification_email: Email address to send notifications to
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER", "")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD", "")
        self.notification_email = notification_email or os.getenv("NOTIFICATION_EMAIL", "")

        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not configured, email notifications disabled")

    def _send_email(self, subject: str, body_html: str, body_text: str) -> bool:
        """
        Send an email.

        Args:
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body content

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.smtp_user or not self.smtp_password or not self.notification_email:
            logger.warning("Email not sent: missing configuration")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.notification_email

            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, self.notification_email, msg.as_string())

            logger.info(f"Email sent successfully: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_failure_alert(
        self,
        video_id: str,
        failure_type: str,
        reason: str | None = None,
        extra_info: dict[str, Any] | None = None,
    ) -> bool:
        """
        Send a failure alert email.

        Args:
            video_id: ID of the failed video
            failure_type: Type of failure (e.g., 'upload_failed', 'manual_required')
            reason: Optional failure reason
            extra_info: Optional extra information to include

        Returns:
            True if sent successfully, False otherwise
        """
        subject = f"[TikTok Auto] Pipeline Failure: {failure_type}"

        # Build HTML body
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #ff4444; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .footer {{ background: #333; color: #aaa; padding: 10px; font-size: 12px; border-radius: 0 0 5px 5px; }}
                .label {{ font-weight: bold; color: #666; }}
                .value {{ margin-left: 10px; }}
                .action {{ background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>⚠️ Pipeline Failure Alert</h2>
                </div>
                <div class="content">
                    <p><span class="label">Failure Type:</span><span class="value">{failure_type}</span></p>
                    <p><span class="label">Video ID:</span><span class="value">{video_id}</span></p>
                    <p><span class="label">Reason:</span><span class="value">{reason or 'Unknown'}</span></p>
                    {"".join(f'<p><span class="label">{k}:</span><span class="value">{v}</span></p>' for k, v in (extra_info or {}).items())}

                    <p style="margin-top: 20px;">
                        Please check the dashboard for more details and take appropriate action.
                    </p>

                    <a href="http://localhost:8080/logs?video_id={video_id}" class="action">
                        View in Dashboard
                    </a>
                </div>
                <div class="footer">
                    <p>TikTok Auto Pipeline | Automated notification</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Build plain text body
        body_text = f"""
TikTok Auto Pipeline - Failure Alert
=====================================

Failure Type: {failure_type}
Video ID: {video_id}
Reason: {reason or 'Unknown'}

{chr(10).join(f'{k}: {v}' for k, v in (extra_info or {}).items())}

Please check the dashboard for more details.
Dashboard: http://localhost:8080/logs?video_id={video_id}
        """

        return self._send_email(subject, body_html, body_text)

    def send_batch_summary(
        self,
        batch_id: str,
        story_title: str,
        total_parts: int,
        successful_parts: int,
        failed_parts: list[dict[str, Any]],
    ) -> bool:
        """
        Send a batch upload summary email.

        Args:
            batch_id: ID of the batch
            story_title: Title of the story
            total_parts: Total number of parts
            successful_parts: Number of successfully uploaded parts
            failed_parts: List of failed parts with details

        Returns:
            True if sent successfully, False otherwise
        """
        status = "✅ Complete" if successful_parts == total_parts else "⚠️ Partial"
        subject = f"[TikTok Auto] Batch {status}: {story_title[:30]}..."

        failed_html = ""
        if failed_parts:
            failed_html = "<h3>Failed Parts:</h3><ul>"
            for part in failed_parts:
                failed_html += f"<li>Part {part.get('part_number', '?')}: {part.get('reason', 'Unknown error')}</li>"
            failed_html += "</ul>"

        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: {'#4CAF50' if successful_parts == total_parts else '#ff9800'}; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .footer {{ background: #333; color: #aaa; padding: 10px; font-size: 12px; border-radius: 0 0 5px 5px; }}
                .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
                .stat {{ text-align: center; }}
                .stat-number {{ font-size: 24px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{status} Batch Upload</h2>
                </div>
                <div class="content">
                    <h3>{story_title}</h3>
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-number">{successful_parts}</div>
                            <div>Successful</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{total_parts - successful_parts}</div>
                            <div>Failed</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{total_parts}</div>
                            <div>Total</div>
                        </div>
                    </div>
                    {failed_html}
                </div>
                <div class="footer">
                    <p>Batch ID: {batch_id}</p>
                </div>
            </div>
        </body>
        </html>
        """

        body_text = f"""
TikTok Auto Pipeline - Batch Summary
=====================================

Story: {story_title}
Status: {status}

Successful: {successful_parts}/{total_parts}
Failed: {total_parts - successful_parts}

Batch ID: {batch_id}
        """

        return self._send_email(subject, body_html, body_text)
