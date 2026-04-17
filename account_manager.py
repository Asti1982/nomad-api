import requests
import os
import random
import string
import time
import re
from dotenv import load_dotenv, set_key

class IdentityManager:
    def __init__(self, env_path=r"c:\Users\Sebastian Höger\Desktop\Nomad\.env"):
        self.env_path = env_path
        self.api_url = "https://api.mail.gw"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        # Ensure the .env file exists to prevent path-related issues with set_key
        if not os.path.exists(self.env_path):
            os.makedirs(os.path.dirname(os.path.abspath(self.env_path)), exist_ok=True)
            with open(self.env_path, 'w') as f:
                f.write("# Arbiter Identity Configuration\n")
        load_dotenv(self.env_path)

    def _generate_random_string(self, length=12):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

    def create_free_email(self):
        """Creates a programmatic email account using Mail.tm API."""
        print("[*] Searching for available email domains...")
        try:
            response = self.session.get(f"{self.api_url}/domains")
            if not response.ok:
                print(f"[!] Failed to get domains: {response.text}")
                return False

            try:
                domains = response.json()
            except Exception:
                print(f"[!] Failed to parse domains JSON: {response.text}")
                return False
                
            member = domains.get('hydra:member') if isinstance(domains, dict) else domains
            if not isinstance(member, list) or not member:
                print("[!] No email domains found.")
                return False

            # Try to pick a domain that looks less like a 'temp' mail if possible
            # Sorting by length can sometimes find more 'normal' looking domains
            sorted_members = sorted(member, key=lambda x: len(x.get('domain', '')) if isinstance(x, dict) else len(str(x)))
            choice = sorted_members[0] 
            domain = choice.get('domain') if isinstance(choice, dict) else str(choice)
            
            # Using a more professional prefix as requested
            base_username = "nomad-arbiter-bot"
            username = f"{base_username}-{self._generate_random_string(4).lower()}"
            email = f"{username}@{domain}"
            password = self._generate_random_string(16)

            print(f"[*] Attempting to create account: {email}")
            payload = {"address": email, "password": password}
            response = self.session.post(f"{self.api_url}/accounts", json=payload)

            if response.status_code == 201:
                print("[+] Email account created successfully.")
                
                # Eventual consistency: Retry token retrieval if account propagation is slow
                token = None
                for attempt in range(10):
                    time.sleep(5)  # Increased delay to give the API more time
                    token_response = self.session.post(f"{self.api_url}/token", json=payload)
                    if token_response.ok:
                        token = token_response.json().get("token")
                        break
                    print(f"[*] Token retrieval attempt {attempt + 1} failed (Status {token_response.status_code}): {token_response.text}")

                if not token:
                    print(f"[!] Failed to retrieve API token after 10 retries. Final error: {token_response.text}")
                    return False

                # Update .env file
                set_key(self.env_path, "GITHUB_EMAIL", str(email))
                set_key(self.env_path, "GITHUB_PASSWORD", str(password))
                set_key(self.env_path, "MAIL_TM_TOKEN", str(token))
                
                # Refresh os.environ so the script can access the new values immediately
                load_dotenv(self.env_path, override=True)
                
                print(f"[!] Credentials saved to {self.env_path}")
                return email
            else:
                print(f"[!] Failed to create account: {response.text}")
                return False
        except Exception as e:
            print(f"[!] Error during email creation: {e}")
            return False

    def setup_github_identity(self):
        """Prepares metadata for GitHub registration."""
        username = "nomad-arbiter"
        set_key(self.env_path, "GITHUB_USERNAME", username)
        email = os.getenv("GITHUB_EMAIL")
        
        print(f"\n" + "="*40)
        print("🚀 ARBITER IDENTITY READY")
        print("="*40)
        print(f"Email: {email}")
        print(f"User:  {username}")
        print("-" * 40)
        print("STEP 1: Go to https://github.com/signup")
        print(f"STEP 2: Use the email and username above.")
        print("STEP 3: Solve the CAPTCHA (Human-in-the-Loop).")
        print("STEP 4: Stay here! I will poll for the verification code.")
        print("="*40)

    def wait_for_verification_code(self):
        """Polls Mail.tm for the GitHub verification code."""
        token = os.getenv("MAIL_TM_TOKEN")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        print("\n[*] Waiting for GitHub verification email... (Auto-polling every 5s)")
        
        while True:
            try:
                response = self.session.get(f"{self.api_url}/messages")
                if not response.ok:
                    time.sleep(5)
                    continue
                    
                resp_data = response.json()
                messages = resp_data.get('hydra:member', []) if isinstance(resp_data, dict) else resp_data
                if not isinstance(messages, list): messages = []
                
                for msg in messages:
                    # Check if the sender or subject looks like GitHub
                    if "GitHub" in msg.get('subject', '') or "github" in msg.get('from', {}).get('address', ''):
                        msg_id = msg['id']
                        print(f"[+] Found email: {msg.get('subject')}. Fetching content...")
                        
                        msg_resp = self.session.get(f"{self.api_url}/messages/{msg_id}")
                        if not msg_resp.ok: continue
                        
                        full_msg = msg_resp.json()
                        body = full_msg.get('text', '') or full_msg.get('intro', '')
                        
                        # Search for a 6 to 8 digit code
                        code_match = re.search(r'(\d{6,8})', body)
                        if code_match:
                            code = code_match.group(1)
                            print(f"\n{'='*30}")
                            print(f"✅ GITHUB VERIFICATION CODE: {code}")
                            print(f"{'='*30}\n")
                            return code
                
                time.sleep(5)
            except Exception as e:
                print(f"[!] Error checking messages: {e}")
                time.sleep(5)

if __name__ == "__main__":
    import sys
    manager = IdentityManager()
    
    try:
        # Check if we already have credentials in .env to allow resuming
        existing_email = os.getenv("GITHUB_EMAIL")
        existing_token = os.getenv("MAIL_TM_TOKEN")
        
        if existing_email and existing_token:
            print(f"[*] Found existing identity: {existing_email}")
            print("[*] Resuming verification process...")
            manager.setup_github_identity()
            manager.wait_for_verification_code()
        else:
            # Create a new email identity
            email_created = manager.create_free_email()
            if email_created:
                manager.setup_github_identity()
                manager.wait_for_verification_code()
            else:
                print("[!] Setup failed. Please check your internet connection or API status.")
                
    except KeyboardInterrupt:
        print("\n\n[!] Process interrupted by user. Exiting safely.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] An unexpected error occurred: {e}")
        sys.exit(1)