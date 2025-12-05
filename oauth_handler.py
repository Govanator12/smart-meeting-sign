# oauth_handler.py - OAuth2 Device Flow Implementation with Watchdog Support
import urequests as requests
import ujson as json
import utime as time
import gc

class OAuth2Handler:
    def __init__(self, client_id, client_secret, scope, token_file, watchdog_callback=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.token_file = token_file
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0

        # Watchdog callback - called to prevent watchdog reset during network ops
        self.feed_watchdog = watchdog_callback if watchdog_callback else lambda: None

        # Retry configuration
        self.max_retries = 3
        self.retry_delays = [5, 10, 20]  # Seconds between retries

        # Try to load existing token
        self.load_token()

    def load_token(self):
        """Load saved refresh token from file"""
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
                self.refresh_token = data.get('refresh_token')
                self.access_token = data.get('access_token')
                self.token_expiry = data.get('expiry', 0)
                print("Loaded saved OAuth token")
                return True
        except:
            print("No saved token found - will need authorization")
            return False

    def save_token(self):
        """Save tokens to file for persistence"""
        try:
            data = {
                'refresh_token': self.refresh_token,
                'access_token': self.access_token,
                'expiry': self.token_expiry
            }
            with open(self.token_file, 'w') as f:
                json.dump(data, f)
            print("Token saved for future use")
            return True
        except Exception as e:
            print(f"Warning: Could not save token: {e}")
            return False

    def _make_request_with_retry(self, url, data, operation_name="request"):
        """
        Make a POST request with retry logic and watchdog feeding.
        Returns (success, result_dict) tuple.
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                self.feed_watchdog()

                if attempt > 0:
                    delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
                    print(f"Retry {attempt}/{self.max_retries - 1} for {operation_name} in {delay}s...")

                    # Feed watchdog during the delay
                    for _ in range(delay):
                        self.feed_watchdog()
                        time.sleep(1)

                self.feed_watchdog()
                print(f"Attempting {operation_name}..." if attempt == 0 else f"Retrying {operation_name}...")

                response = requests.post(
                    url,
                    json=data,
                    headers={'Content-Type': 'application/json'}
                )

                self.feed_watchdog()
                result = response.json()
                response.close()
                gc.collect()
                self.feed_watchdog()

                # Check for errors that should trigger retry
                if 'error' in result:
                    error = result.get('error', 'Unknown')
                    error_desc = result.get('error_description', '')

                    # These errors are not retryable
                    if error in ['invalid_grant', 'invalid_client', 'unauthorized_client']:
                        print(f"{operation_name} failed (not retryable): {error}")
                        return (False, result)

                    # Authorization pending is expected during device flow
                    if error == 'authorization_pending':
                        return (True, result)

                    # Other errors - retry
                    print(f"{operation_name} error: {error} {error_desc}")
                    last_error = error
                    continue

                # Success
                return (True, result)

            except Exception as e:
                last_error = str(e)
                print(f"{operation_name} exception: {e}")
                self.feed_watchdog()
                gc.collect()
                continue

        # All retries exhausted
        print(f"{operation_name} failed after {self.max_retries} attempts. Last error: {last_error}")
        return (False, {'error': last_error})

    def device_authorization(self):
        """Start OAuth2 device flow - one-time setup"""
        print("\n" + "="*50)
        print("      FIRST TIME SETUP - AUTHORIZATION NEEDED")
        print("="*50)

        # Request device code
        data = {
            'client_id': self.client_id,
            'scope': self.scope
        }

        success, result = self._make_request_with_retry(
            "https://oauth2.googleapis.com/device/code",
            data,
            "device code request"
        )

        if not success or 'error' in result:
            print(f"Error getting device code: {result.get('error', 'Unknown')}")
            return False

        device_code = result['device_code']
        user_code = result['user_code']
        verification_url = result['verification_url']
        interval = result.get('interval', 5)
        expires_in = result.get('expires_in', 600)

        print("\nTO AUTHORIZE THIS DEVICE:")
        print(f"\n1. On your computer/phone, visit:\n   {verification_url}")
        print(f"\n2. Enter this code: {user_code}")
        print("\n3. Sign in and grant calendar access")
        print(f"\nYou have {expires_in//60} minutes to complete this")
        print("="*50 + "\n")

        # Poll for authorization
        print("Waiting for authorization", end="")
        start_time = time.time()

        while time.time() - start_time < expires_in:
            # Feed watchdog during wait
            for _ in range(interval):
                self.feed_watchdog()
                time.sleep(1)
            print(".", end="")

            # Check if user has authorized
            token_data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'device_code': device_code,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            }

            self.feed_watchdog()

            try:
                response = requests.post(
                    "https://oauth2.googleapis.com/token",
                    json=token_data,
                    headers={'Content-Type': 'application/json'}
                )

                self.feed_watchdog()
                result = response.json()
                response.close()
                gc.collect()

                if 'access_token' in result:
                    # Success!
                    self.access_token = result['access_token']
                    self.refresh_token = result['refresh_token']
                    self.token_expiry = time.time() + result.get('expires_in', 3600)
                    self.save_token()
                    print("\nAuthorization successful! Device is now linked.")
                    print("You won't need to do this again.\n")
                    return True
                elif result.get('error') == 'authorization_pending':
                    # User hasn't authorized yet
                    continue
                elif result.get('error') == 'slow_down':
                    # Need to slow down polling
                    interval += 2
                else:
                    print(f"\nAuthorization error: {result.get('error', 'Unknown')}")
                    return False

            except Exception as e:
                print(f"\nPolling error: {e}")
                self.feed_watchdog()
                # Continue polling despite error
                continue

        print("\nAuthorization timeout - please try again")
        return False

    def refresh_access_token(self):
        """Refresh the access token using saved refresh token with retry logic"""
        if not self.refresh_token:
            print("No refresh token - need new authorization")
            return self.device_authorization()

        print("Refreshing access token...")

        token_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }

        success, result = self._make_request_with_retry(
            "https://oauth2.googleapis.com/token",
            token_data,
            "token refresh"
        )

        if success and 'access_token' in result:
            self.access_token = result['access_token']
            self.token_expiry = time.time() + result.get('expires_in', 3600)
            # Note: Refresh token doesn't change
            self.save_token()
            print("Token refreshed successfully")
            return True
        else:
            error = result.get('error', 'Unknown')
            print(f"Token refresh failed: {error}")

            # If refresh fails with invalid_grant, try new authorization
            if error == 'invalid_grant':
                print("Refresh token expired - need new authorization")
                self.refresh_token = None
                return self.device_authorization()

            return False

    def get_valid_token(self):
        """Get a valid access token, refreshing if needed"""
        self.feed_watchdog()

        # Check if token exists and is valid (with 5 min buffer)
        if self.access_token and time.time() < (self.token_expiry - 300):
            return self.access_token

        # Try to refresh using saved refresh token
        if self.refresh_token:
            if self.refresh_access_token():
                return self.access_token

        # Need new authorization (first time or refresh failed)
        if self.device_authorization():
            return self.access_token

        return None
