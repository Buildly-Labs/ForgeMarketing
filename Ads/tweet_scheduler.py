import requests
from requests_oauthlib import OAuth1Session
import webbrowser
import random
import time
import os

# Twitter credentials - set via environment variables
consumer_key = os.environ.get('TWITTER_CONSUMER_KEY', '')
consumer_secret = os.environ.get('TWITTER_CONSUMER_SECRET', '')
bearer_token = os.environ.get('TWITTER_BEARER_TOKEN', '')
access_token = os.environ.get('TWITTER_ACCESS_TOKEN', '')
access_token_secret = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET', '')

# Define the ad variations
ads = [
    "Plan content, approvals, and scheduling in one place. A calm workflow keeps marketing moving. https://example.com/forgemarketing",
    "Turn campaign ideas into drafts, review notes, and next steps without losing track of the work. https://example.com/forgemarketing",
    "Use simple checklists for manual posting, account setup, and weekly performance review. https://example.com/forgemarketing",
    "Keep brand voice, assets, and platform drafts together so your team can move faster. https://example.com/forgemarketing",
    "Human-in-the-loop marketing works better than automation when approval matters. https://example.com/forgemarketing",
    # Additional ad variations go here
    "Track what is drafted, approved, scheduled, posted, and ready for performance checks. https://example.com/forgemarketing",
    "A marketing command center for interns and founder-led teams. https://example.com/forgemarketing",
    "Create platform-specific drafts, attach assets, and keep humans responsible for publishing. https://example.com/forgemarketing",
    "Manage campaigns with clear owners, due dates, and notes for every manual task. https://example.com/forgemarketing",
    "Keep content organized across platforms without risky automation. https://example.com/forgemarketing"
]

# Initialize OAuth
oauth = OAuth1Session(consumer_key, client_secret=consumer_secret)
fetch_response = oauth.fetch_request_token("https://api.twitter.com/oauth/request_token")
resource_owner_key = fetch_response.get('oauth_token')
resource_owner_secret = fetch_response.get('oauth_token_secret')

# Authorization
full_authorize_url = oauth.authorization_url("https://api.twitter.com/oauth/authorize")
webbrowser.open(full_authorize_url)
verifier = input('Please enter the PIN: ')

# Obtain Access Token
oauth = OAuth1Session(consumer_key,
                      client_secret=consumer_secret,
                      resource_owner_key=resource_owner_key,
                      resource_owner_secret=resource_owner_secret,
                      verifier=verifier)
oauth_tokens = oauth.fetch_access_token("https://api.twitter.com/oauth/access_token")

access_token = oauth_tokens['oauth_token']
access_token_secret = oauth_tokens['oauth_token_secret']

# Function to post tweets
def post_tweet(oauth_session, text):
    response = oauth_session.post("https://api.twitter.com/2/tweets", json={"text": text})
    if response.status_code == 201:
        print("Tweet posted successfully!")
    else:
        print("Failed to post tweet:", response.content)

# Post tweets every hour
oauth = OAuth1Session(consumer_key,
                      client_secret=consumer_secret,
                      resource_owner_key=access_token,
                      resource_owner_secret=access_token_secret)

for i in range(1000):
    post_tweet(oauth, random.choice(ads))
    time.sleep(3600)  # Wait for 1 hour
