"""Tests for email notification module."""

from unittest.mock import patch


class TestEmailNotifier:
    """Tests for EmailNotifier class."""

    def test_notifier_init_with_env_vars(self, monkeypatch):
        """Test that notifier uses environment variables."""
        monkeypatch.setenv("SMTP_HOST", "test.smtp.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "test@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "testpass")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "notify@example.com")

        from shared.python.email import EmailNotifier

        notifier = EmailNotifier()

        assert notifier.smtp_host == "test.smtp.com"
        assert notifier.smtp_port == 465
        assert notifier.smtp_user == "test@example.com"
        assert notifier.smtp_password == "testpass"
        assert notifier.notification_email == "notify@example.com"

    def test_notifier_init_with_args(self):
        """Test that notifier can be initialized with explicit args."""
        from shared.python.email import EmailNotifier

        notifier = EmailNotifier(
            smtp_host="custom.smtp.com",
            smtp_port=587,
            smtp_user="custom@example.com",
            smtp_password="custompass",
            notification_email="custom-notify@example.com",
        )

        assert notifier.smtp_host == "custom.smtp.com"
        assert notifier.smtp_port == 587

    def test_send_failure_alert(self, mock_smtp, monkeypatch):
        """Test sending a failure alert."""
        monkeypatch.setenv("SMTP_USER", "test@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "testpass")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "notify@example.com")

        from shared.python.email import EmailNotifier

        notifier = EmailNotifier()
        result = notifier.send_failure_alert(
            video_id="test-video-123",
            failure_type="upload_failed",
            reason="Connection timeout",
        )

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()
        mock_smtp.sendmail.assert_called_once()

    def test_send_failure_alert_without_credentials(self, monkeypatch):
        """Test that send_failure_alert returns False without credentials."""
        monkeypatch.setenv("SMTP_USER", "")
        monkeypatch.setenv("SMTP_PASSWORD", "")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "")

        from shared.python.email import EmailNotifier

        notifier = EmailNotifier()
        result = notifier.send_failure_alert(
            video_id="test-video-123",
            failure_type="upload_failed",
        )

        assert result is False

    def test_send_failure_alert_with_extra_info(self, mock_smtp, monkeypatch):
        """Test that extra_info is included in the email."""
        monkeypatch.setenv("SMTP_USER", "test@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "testpass")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "notify@example.com")

        from shared.python.email import EmailNotifier

        notifier = EmailNotifier()
        result = notifier.send_failure_alert(
            video_id="test-video-123",
            failure_type="upload_failed",
            reason="Connection timeout",
            extra_info={"story_title": "Test Story", "part_number": 2},
        )

        assert result is True
        # Verify sendmail was called with content containing extra info
        call_args = mock_smtp.sendmail.call_args
        email_content = call_args[0][2]  # Third argument is the message
        assert "story_title" in email_content or "Test Story" in email_content

    def test_send_batch_summary_complete(self, mock_smtp, monkeypatch):
        """Test sending a complete batch summary."""
        monkeypatch.setenv("SMTP_USER", "test@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "testpass")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "notify@example.com")

        from shared.python.email import EmailNotifier

        notifier = EmailNotifier()
        result = notifier.send_batch_summary(
            batch_id="batch-123",
            story_title="Test Story Title",
            total_parts=3,
            successful_parts=3,
            failed_parts=[],
        )

        assert result is True
        call_args = mock_smtp.sendmail.call_args
        email_content = call_args[0][2]
        assert "Complete" in email_content

    def test_send_batch_summary_partial(self, mock_smtp, monkeypatch):
        """Test sending a partial batch summary."""
        monkeypatch.setenv("SMTP_USER", "test@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "testpass")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "notify@example.com")

        from shared.python.email import EmailNotifier

        notifier = EmailNotifier()
        result = notifier.send_batch_summary(
            batch_id="batch-456",
            story_title="Partial Story",
            total_parts=3,
            successful_parts=2,
            failed_parts=[{"part_number": 3, "reason": "Upload timeout"}],
        )

        assert result is True
        call_args = mock_smtp.sendmail.call_args
        email_content = call_args[0][2]
        assert "Partial" in email_content

    def test_send_email_handles_smtp_error(self, monkeypatch):
        """Test that SMTP errors are handled gracefully."""
        monkeypatch.setenv("SMTP_USER", "test@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "testpass")
        monkeypatch.setenv("NOTIFICATION_EMAIL", "notify@example.com")

        from shared.python.email import EmailNotifier

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp_class.side_effect = ConnectionRefusedError("Connection refused")

            notifier = EmailNotifier()
            result = notifier.send_failure_alert(
                video_id="test-video-123",
                failure_type="upload_failed",
            )

            assert result is False
