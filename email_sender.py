import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

class EmailSender:
    def __init__(self):
        self.sender_email = os.getenv("EMAIL_SENDER_ADDRESS")
        self.sender_password = os.getenv("EMAIL_SENDER_PASSWORD")
        self.smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", 587)) # 587 for TLS, 465 for SSL

    def send_email(self, recipient_email: str, subject: str, body: str):
        if not self.sender_email or not self.sender_password:
            print("Email sender credentials not configured. Skipping email.")
            return False

        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()  # Secure the connection
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            print(f"Email sent successfully to {recipient_email}")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False