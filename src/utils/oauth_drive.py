REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"

def create_auth_url(credentials_file, scopes):
    flow = Flow.from_client_secrets_file(
        credentials_file,
        scopes=scopes,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url

def fetch_and_store_credentials(credentials_file, scopes, request_url):
    flow = Flow.from_client_secrets_file(
        credentials_file,
        scopes=scopes,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(authorization_response=request_url)
    creds = flow.credentials
    with open("token.pkl", "wb") as f:
        pickle.dump(creds, f)
    return creds
