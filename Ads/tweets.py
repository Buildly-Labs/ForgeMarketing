import requests
import random
import time
import json
import os

# Twitter credentials - set via environment variables
bearer_token = os.environ.get('TWITTER_BEARER_TOKEN', '')

# Headers for the HTTP requests
headers = {
    'Authorization': f'Bearer {bearer_token}',
    'Content-Type': 'application/json',
}

# Function to create a tweet
def create_tweet(text):
    url = 'https://api.twitter.com/2/tweets'
    payload = {
        'text': text
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

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

# Function to post tweets
def post_tweet():
    ad = random.choice(ads)
    try:
        response = create_tweet(ad)
        print(f"Tweet posted successfully: {response}")
    except Exception as e:
        print(f"An error occurred: {e}")

# Loop to post tweets every hour
for _ in range(200):
    post_tweet()
    time.sleep(3600)  # Wait for 1 hour

