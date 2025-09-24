# oauth_handler.py - OAuth2 Device Flow Implementation
import urequests as requests
import ujson as json
import utime as time
import gc

class OAuth2Handler:
    def __init__(self, client_id, client_secret, scope, token_file):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.token_file = token_file
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0
        
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
                print("✓ Loaded saved OAuth token")
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
            print("✓ Token saved for future use")
            return True
        except Exception as e:
            print(f"Warning: Could not save token: {e}")
            return False
    
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
        
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/device/code",
                json=data,
                headers={'Content-Type': 'application/json'}
            )
            
            result = response.json()
            response.close()
            gc.collect()
            
            if 'error' in result:
                print(f"Error getting device code: {result['error']}")
                return False
            
            device_code = result['device_code']
            user_code = result['user_code']
            verification_url = result['verification_url']
            interval = result.get('interval', 5)
            expires_in = result.get('expires_in', 600)
            
            print("\n📱 TO AUTHORIZE THIS DEVICE:")
            print(f"\n1. On your computer/phone, visit:\n   {verification_url}")
            print(f"\n2. Enter this code: {user_code}")
            print("\n3. Sign in and grant calendar access")
            print(f"\n⏰ You have {expires_in//60} minutes to complete this")
            print("="*50 + "\n")
            
            # Poll for authorization
            print("Waiting for authorization", end="")
            start_time = time.time()
            
            while time.time() - start_time < expires_in:
                time.sleep(interval)
                print(".", end="")
                
                # Check if user has authorized
                token_data = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'device_code': device_code,
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
                }
                
                response = requests.post(
                    "https://oauth2.googleapis.com/token",
                    json=token_data,
                    headers={'Content-Type': 'application/json'}
                )
                
                result = response.json()
                response.close()
                gc.collect()
                
                if 'access_token' in result:
                    # Success!
                    self.access_token = result['access_token']
                    self.refresh_token = result['refresh_token']
                    self.token_expiry = time.time() + result.get('expires_in', 3600)
                    self.save_token()
                    print("\n✅ Authorization successful! Device is now linked.")
                    print("You won't need to do this again.\n")
                    return True
                elif result.get('error') == 'authorization_pending':
                    # User hasn't authorized yet
                    continue
                elif result.get('error') == 'slow_down':
                    # Need to slow down polling
                    interval += 2
                else:
                    print(f"\n❌ Authorization error: {result.get('error', 'Unknown')}")
                    return False
            
            print("\n❌ Authorization timeout - please try again")
            return False
            
        except Exception as e:
            print(f"Authorization error: {e}")
            gc.collect()
            return False
    
    def refresh_access_token(self):
        """Refresh the access token using saved refresh token"""
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
        
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                json=token_data,
                headers={'Content-Type': 'application/json'}
            )
            
            result = response.json()
            response.close()
            gc.collect()
            
            if 'access_token' in result:
                self.access_token = result['access_token']
                self.token_expiry = time.time() + result.get('expires_in', 3600)
                # Note: Refresh token doesn't change
                self.save_token()
                print("✓ Token refreshed")
                return True
            else:
                print(f"Token refresh failed: {result.get('error', 'Unknown')}")
                # If refresh fails, try new authorization
                if result.get('error') == 'invalid_grant':
                    print("Refresh token expired - need new authorization")
                    self.refresh_token = None
                    return self.device_authorization()
                return False
                
        except Exception as e:
            print(f"Refresh error: {e}")
            gc.collect()
            return False
    
    def get_valid_token(self):
        """Get a valid access token, refreshing if needed"""
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
