# main.py
import os
import time
import random
import logging
import json
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env from the config directory relative to this script
    env_path = os.path.join(os.path.dirname(__file__), '..', 'config', '.env.post-scraper')
    load_dotenv(env_path)
except ImportError:
    # If python-dotenv is not available, try to load manually
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', 'config', '.env.post-scraper')
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    if key.startswith('export '):
                        key = key[7:]  # Remove 'export ' prefix
                    # Remove quotes if present
                    value = value.strip('"\'')
                    os.environ[key] = value
    except FileNotFoundError:
        print("Warning: .env.post-scraper file not found in config directory")

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

def get_credentials():
    username = os.environ.get('TWITTER_USERNAME')
    password = os.environ.get('TWITTER_PASSWORD')
    email = os.environ.get('TWITTER_EMAIL')
    if not username or not password:
        raise ValueError("Set TWITTER_USERNAME and TWITTER_PASSWORD environment variables.")
    return username, password, email

def parse_tweet_date(page):
    """Extract tweet date from the current tweet page"""
    try:
        # Try to get the time element with datetime attribute
        time_element = page.query_selector('time[datetime]')
        if time_element:
            datetime_str = time_element.get_attribute('datetime')
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        
        # Fallback: try to get readable time text
        time_element = page.query_selector('time')
        if time_element:
            time_text = time_element.inner_text().strip()
            # Handle relative times like "2h", "1d", "3w", "2m", "1y"
            if 'h' in time_text and time_text.replace('h', '').isdigit():
                hours_ago = int(time_text.replace('h', ''))
                return datetime.now() - timedelta(hours=hours_ago)
            elif 'd' in time_text and time_text.replace('d', '').isdigit():
                days_ago = int(time_text.replace('d', ''))
                return datetime.now() - timedelta(days=days_ago)
            elif 'w' in time_text and time_text.replace('w', '').isdigit():
                weeks_ago = int(time_text.replace('w', ''))
                return datetime.now() - timedelta(weeks=weeks_ago)
            elif time_text.endswith('min') or (time_text.endswith('m') and len(time_text) <= 3 and int(time_text[:-1]) <= 59):
                minutes_ago = int(time_text.replace('min', '').replace('m', ''))
                return datetime.now() - timedelta(minutes=minutes_ago)
            elif 'month' in time_text.lower() or time_text.endswith('mo'):
                months_ago = int(''.join(filter(str.isdigit, time_text)))
                return datetime.now() - timedelta(days=months_ago * 30)  # Approximate
            elif 'y' in time_text and time_text.replace('y', '').isdigit():
                years_ago = int(time_text.replace('y', ''))
                return datetime.now() - timedelta(days=years_ago * 365)  # Approximate
        
        return None
    except Exception as e:
        logging.warning(f"Failed to parse tweet date: {e}")
        return None

def is_date_in_range(tweet_date, start_date=None, end_date=None):
    """Check if tweet date falls within the specified date range"""
    if not tweet_date:
        return True  # If we can't determine date, include it
    
    # Convert string dates to datetime objects if needed
    if start_date and isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if end_date and isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        # Set end_date to end of day
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    # Remove timezone info for comparison if present
    if tweet_date.tzinfo:
        tweet_date = tweet_date.replace(tzinfo=None)
    
    if start_date and tweet_date < start_date:
        return False
    if end_date and tweet_date > end_date:
        return False
    
    return True

def normalize_tweet_url(url):
    """Remove /photo/X, /video/X, /analytics, /media_tags and other suffixes from tweet URLs to avoid duplicates"""
    import re
    # Remove photo, video, analytics, media_tags and other media-related suffixes
    url = re.sub(r'/(photo|video)/\d+$', '', url)
    url = re.sub(r'/(analytics|media_tags|media)$', '', url)
    url = re.sub(r'/likes$', '', url)
    url = re.sub(r'/retweets$', '', url)
    url = re.sub(r'/quotes$', '', url)
    return url

def robust_wait(page, selector, timeout=15000):
    """Enhanced wait with multiple strategies"""
    for interval in [3000, 5000, timeout]:
        try:
            page.wait_for_selector(selector, timeout=interval)
            return True
        except PlaywrightTimeout:
            # Try scrolling to trigger content loading
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 0);")
                page.wait_for_selector(selector, timeout=2000)
                return True
            except PlaywrightTimeout:
                continue
    return False

def login_x(page, username, password, email=None):
    """Enhanced login with better error handling"""
    try:
        logging.info("Attempting to login to Twitter/X...")
        page.goto("https://x.com/login", timeout=45000, wait_until='load')
        
        # Wait for login form
        if not robust_wait(page, 'input[name="text"]', timeout=20000): 
            logging.error("Login form not found")
            return False
            
        # Fill username
        page.fill('input[name="text"]', username)
        page.click('text=Next')
        time.sleep(random.uniform(2, 4))
        
        # Handle email verification if required
        try:
            if page.is_visible('input[name="text"]', timeout=5000):
                logging.info("Email verification required")
                if email:
                    page.fill('input[name="text"]', email)
                    page.click('text=Next')
                    time.sleep(random.uniform(2, 4))
                else:
                    logging.error("Extra verification required but email not provided.")
                    return False
        except PlaywrightTimeout: 
            pass
        
        # Fill password
        if robust_wait(page, 'input[name="password"]', timeout=10000):
            page.fill('input[name="password"]', password)
            page.click('text=Log in')
            time.sleep(random.uniform(3, 5))
        else: 
            logging.error("Password field not found")
            return False
            
        # Verify login success
        if not robust_wait(page, '[aria-label="Account menu"]', timeout=20000): 
            logging.error("Login verification failed")
            return False
            
        logging.info("Login successful!")
        time.sleep(random.uniform(2, 4))
        return True
        
    except Exception as e:
        logging.error(f"Login failed with error: {e}")
        return False

def check_profile_accessibility(page, profile_url, max_retries=3):
    """Check if profile is accessible and return status"""
    for attempt in range(max_retries):
        try:
            logging.info(f"Checking profile accessibility: {profile_url} (attempt {attempt + 1}/{max_retries})")
            
            # Navigate with longer timeout and retry
            page.goto(profile_url, timeout=45000, wait_until='domcontentloaded')
            
            # Check for various error conditions
            time.sleep(random.uniform(2, 4))
            
            # Check if profile is suspended
            if page.query_selector("text=Account suspended"):
                return "suspended"
            
            # Check if profile doesn't exist
            if page.query_selector("text=This account doesn't exist"):
                return "not_found"
                
            # Check if profile is protected
            if page.query_selector("[data-testid='ProtectedBadge']") or page.query_selector("text=These Tweets are protected"):
                return "protected"
                
            # Check if we're rate limited or blocked
            if page.query_selector("text=Rate limit exceeded") or page.query_selector("text=Something went wrong"):
                logging.warning(f"Rate limit or error detected for {profile_url}, retrying after delay...")
                time.sleep(random.uniform(10, 20))
                continue
                
            # Check if tweets are present
            if robust_wait(page, "[data-testid='tweet']", timeout=15000):
                return "accessible"
            else:
                # Maybe no tweets in timeframe, but profile exists
                if page.query_selector("[data-testid='UserName']") or page.query_selector("[data-testid='UserDescription']"):
                    return "no_tweets"
                else:
                    return "unknown_error"
                    
        except Exception as e:
            logging.warning(f"Error checking profile {profile_url} (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 10))
                continue
            return "error"
    
    return "timeout"

def scrape_keyword_posts(profile_url, keywords, page, start_date=None, end_date=None, max_scrolls=5, scroll_delay=3, early_stop_on_old_tweets=True):
    """OPTIMIZED: Extract all data from timeline without individual page visits - FIXES DOM STALENESS"""
    keywords = [k.lower() for k in keywords]
    matched_posts = {k: set() for k in keywords}
    tweet_contents = {}
    tweet_dates = {}
    
    # Convert date strings once
    start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end_date else None
    
    # Check profile accessibility first
    profile_status = check_profile_accessibility(page, profile_url)
    if profile_status != "accessible":
        logging.warning(f"Profile {profile_url} is {profile_status}, skipping...")
        return {k: list(v) for k, v in matched_posts.items()}, tweet_contents, tweet_dates
    
    processed_urls = set()
    tweets_processed = 0
    tweets_in_date_range = 0
    consecutive_old_tweets = 0
    scroll_count = 0
    
    time.sleep(random.uniform(3, 7))
    
    # Main scrolling loop - NO PAGE NAVIGATION (STAYS ON TIMELINE)
    while scroll_count < max_scrolls:
        tweet_elements = page.query_selector_all("[data-testid='tweet']")
        logging.info(f"Found {len(tweet_elements)} tweet elements on scroll {scroll_count + 1}")
        
        new_tweets_found = False
        
        # Process ALL tweets in current view WITHOUT navigating away
        for i, tweet_element in enumerate(tweet_elements):
            try:
                # STEP 1: Extract URL (same as before)
                tweet_links = tweet_element.query_selector_all("a[href*='/status/']")
                if not tweet_links:
                    continue
                
                original_url = None
                for link in tweet_links:
                    href = link.get_attribute('href')
                    if href and 'analytics' not in href and '/status/' in href:
                        original_url = href
                        break
                
                if not original_url:
                    continue
                    
                if original_url.startswith('/'):
                    original_url = f"https://x.com{original_url}"
                    
                normalized_url = normalize_tweet_url(original_url)
                
                # Skip if already processed
                if normalized_url in processed_urls:
                    continue
                    
                processed_urls.add(normalized_url)
                new_tweets_found = True
                
                # STEP 2: Extract date FROM TIMELINE (no navigation needed)
                tweet_date = None
                try:
                    time_element = tweet_element.query_selector('time[datetime]')
                    if time_element:
                        datetime_str = time_element.get_attribute('datetime')
                        tweet_date = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                        
                        if tweet_date.tzinfo:
                            tweet_date = tweet_date.replace(tzinfo=None)
                        
                        # Date range filtering
                        if start_dt and tweet_date < start_dt:
                            logging.debug(f"Tweet {normalized_url} too old, skipping")
                            consecutive_old_tweets += 1
                            if early_stop_on_old_tweets and consecutive_old_tweets >= 5:
                                logging.info(f"Found 5 consecutive old tweets, stopping early")
                                return {k: list(v) for k, v in matched_posts.items()}, tweet_contents, tweet_dates
                            continue
                        if end_dt and tweet_date > end_dt:
                            logging.debug(f"Tweet {normalized_url} too new, skipping")
                            continue
                            
                        consecutive_old_tweets = 0  # Reset on valid date
                except Exception as e:
                    logging.debug(f"Date parsing failed for {normalized_url}: {e}")
                    # If we can't parse date and date filtering is enabled, skip cautiously
                    if start_dt or end_dt:
                        consecutive_old_tweets += 1
                        if early_stop_on_old_tweets and consecutive_old_tweets >= 8:
                            logging.info(f"Too many unparseable dates, stopping")
                            return {k: list(v) for k, v in matched_posts.items()}, tweet_contents, tweet_dates
                        continue
                
                tweets_in_date_range += 1
                
                # STEP 3: Extract content FROM TIMELINE (THE KEY FIX - NO NAVIGATION!)
                tweet_text = None
                
                try:
                    # Handle "Show more" expansion (critical for finding keywords)
                    show_more_buttons = tweet_element.query_selector_all("div[role='button']")
                    for btn in show_more_buttons:
                        try:
                            btn_text = btn.inner_text().lower()
                            if 'show more' in btn_text or 'read more' in btn_text:
                                logging.debug(f"Expanding truncated tweet {normalized_url}")
                                btn.click()
                                time.sleep(0.5)  # Wait for expansion
                                break
                        except:
                            continue
                    
                    # Primary method: Get tweetText from timeline
                    content_element = tweet_element.query_selector("[data-testid='tweetText']")
                    if content_element:
                        tweet_text = content_element.inner_text().strip()
                    
                    # Fallback 1: Try article > div with lang attribute
                    if not tweet_text or len(tweet_text) < 10:
                        article = tweet_element.query_selector("article")
                        if article:
                            lang_elements = article.query_selector_all("[lang]")
                            text_parts = []
                            for elem in lang_elements:
                                text = elem.inner_text().strip()
                                # Filter out UI elements
                                if len(text) > 10 and not any(x in text.lower() for x in ['reply', 'retweet', 'like', 'bookmark', 'follow']):
                                    text_parts.append(text)
                            if text_parts:
                                tweet_text = " ".join(text_parts[:3])  # First 3 meaningful parts
                    
                    # Fallback 2: Get longest span with lang attribute
                    if not tweet_text or len(tweet_text) < 10:
                        spans = tweet_element.query_selector_all("span[lang]")
                        longest = ""
                        for span in spans:
                            text = span.inner_text().strip()
                            if len(text) > len(longest) and not any(x in text.lower() for x in ['reply', 'retweet', 'like', 'bookmark']):
                                longest = text
                        if len(longest) > 10:
                            tweet_text = longest
                    
                    if not tweet_text or len(tweet_text) < 5:
                        logging.debug(f"Content extraction failed for {normalized_url}")
                        continue
                        
                except Exception as e:
                    logging.debug(f"Error extracting content from timeline for {normalized_url}: {e}")
                    continue
                
                tweets_processed += 1
                
                # STEP 4: Store content and date
                tweet_contents[normalized_url] = tweet_text
                if tweet_date:
                    tweet_dates[normalized_url] = tweet_date.strftime('%Y-%m-%d')
                else:
                    tweet_dates[normalized_url] = "Unknown"
                
                # STEP 5: Keyword matching
                tweet_text_lower = tweet_text.lower()
                matched_keywords = []
                
                for kw in keywords:
                    if kw in tweet_text_lower:
                        matched_posts[kw].add(normalized_url)
                        matched_keywords.append(kw)
                
                if matched_keywords:
                    logging.info(f"✅ Found keywords {matched_keywords} in tweet: {normalized_url}")
                    logging.debug(f"Tweet content preview: {tweet_text[:100]}...")
                
            except Exception as e:
                logging.debug(f"Error processing tweet element {i}: {e}")
                continue
        
        # Log statistics for this scroll (helps debug keyword matching)
        total_matches = sum(len(v) for v in matched_posts.values())
        logging.info(f"📊 Scroll {scroll_count + 1}: processed={tweets_processed}, in_date_range={tweets_in_date_range}, matched={total_matches}")
        
        # Stop if no new tweets found
        if not new_tweets_found:
            logging.info(f"No new tweets found on scroll {scroll_count + 1}, stopping")
            break
        
        # Scroll to load more tweets
        scroll_count += 1
        if scroll_count < max_scrolls:
            logging.info(f"Scrolling to load more tweets... (scroll {scroll_count}/{max_scrolls})")
            
            old_height = page.evaluate("document.body.scrollHeight")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_delay)
            
            # Wait for new content to load
            try:
                page.wait_for_function(
                    f"() => document.body.scrollHeight > {old_height}",
                    timeout=5000
                )
            except PlaywrightTimeout:
                logging.info("No new content loaded after scrolling")
    
    total_matches = sum(len(v) for v in matched_posts.values())
    logging.info(f"✅ COMPLETED {profile_url}: processed={tweets_processed}, in_date_range={tweets_in_date_range}, matched={total_matches}")
    return {k: list(v) for k, v in matched_posts.items()}, tweet_contents, tweet_dates

def load_config_json(filepath):
    with open(filepath, 'r') as f:
        config = json.load(f)
    return (
        config.get('profiles', []), 
        config.get('keywords', []),
        config.get('start_date', None),
        config.get('end_date', None),
        config.get('max_scrolls', 5),  # Default to 5 scrolls
        config.get('scroll_delay', 3),  # Default to 3 seconds between scrolls
        config.get('early_stop_on_old_tweets', True)  # Default to early stopping
    )

if __name__ == "__main__":
    import sys
    config_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'input', 'profiles_and_keywords.json')
    profiles, keywords, start_date, end_date, max_scrolls, scroll_delay, early_stop_on_old_tweets = load_config_json(config_file)
    
    # Log date range if specified
    if start_date or end_date:
        date_info = f"Date range: {start_date or 'beginning'} to {end_date or 'now'}"
        logging.info(date_info)
    else:
        logging.info("No date filtering applied - scraping all available tweets")
    
    # Log scraping configuration
    logging.info(f"Scraping configuration: max_scrolls={max_scrolls}, scroll_delay={scroll_delay}s, early_stop={early_stop_on_old_tweets}")
    
    username, password, email = get_credentials()
    results = {}
    all_tweet_contents = {}  # Store all tweet contents
    all_tweet_dates = {}  # Store all tweet dates
    
    # User agents for rotation
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    ]
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        # Use random user agent
        selected_user_agent = random.choice(user_agents)
        logging.info(f"Using user agent: {selected_user_agent[:50]}...")
        
        context = browser.new_context(
            user_agent=selected_user_agent,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York'
        )
        page = context.new_page()
        
        # Speed optimization: Block heavy resources (images, videos, media)
        def handle_route(route):
            resource_type = route.request.resource_type
            if resource_type in ["image", "media", "font", "stylesheet"]:
                route.abort()
            else:
                route.continue_()
        
        page.route("**/*", handle_route)
        
        try:
            if not login_x(page, username, password, email):
                logging.error("Login failed. Exiting.")
                exit()
            
            profile_count = 0
            for profile in profiles:
                profile_count += 1
                logging.info(f"Processing profile {profile_count}/{len(profiles)}: {profile}")
                
                try:
                    profile_results, profile_contents, profile_dates = scrape_keyword_posts(
                        profile, keywords, page, start_date, end_date, 
                        max_scrolls, scroll_delay, early_stop_on_old_tweets
                    )
                    results[profile] = profile_results
                    all_tweet_contents.update(profile_contents)
                    all_tweet_dates.update(profile_dates)
                    
                    # Add delay between profiles to avoid rate limiting
                    if profile_count < len(profiles):  # Don't delay after last profile
                        delay = random.uniform(5, 15)
                        logging.info(f"Waiting {delay:.1f}s before next profile...")
                        time.sleep(delay)
                        
                except Exception as profile_error:
                    logging.error(f"Error processing profile {profile}: {profile_error}")
                    continue
                    
        except Exception as e:
            logging.exception(f"Error during scraping: {e}")
        finally:
            browser.close()
    
    # Print results for review
    print("\n" + "="*50)
    print("SCRAPING RESULTS:")
    print("="*50)
    
    # Create consolidated view for display
    profile_url_keywords = {}  # {profile: {url: set(keywords)}}
    
    for profile, kwdata in results.items():
        if profile not in profile_url_keywords:
            profile_url_keywords[profile] = {}
        for keyword, urls in kwdata.items():
            for url in urls:
                if url not in profile_url_keywords[profile]:
                    profile_url_keywords[profile][url] = set()
                profile_url_keywords[profile][url].add(keyword)
    
    total_matches = 0
    for profile, url_kw_data in profile_url_keywords.items():
        print(f"\n📱 Profile: {profile}")
        for url, keywords in url_kw_data.items():
            tweet_content = all_tweet_contents.get(url, "Content not available")
            tweet_date = all_tweet_dates.get(url, "Unknown date")
            # Truncate content for display (first 100 characters)
            display_content = tweet_content[:100] + "..." if len(tweet_content) > 100 else tweet_content
            keywords_str = ", ".join(sorted(keywords))
            print(f"  🔍 Keywords: '{keywords_str}'")
            print(f"    📅 Date: {tweet_date}")
            print(f"    → {url}")
            print(f"      📝 {display_content}")
            total_matches += 1
    
    print(f"\n🎯 Total matches found: {total_matches}")
    print("="*50)
    
    # Always export results to CSV
    import csv
    import os
    end_date_str = end_date if end_date else datetime.now().strftime("%Y%m%d")
    results_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'output')
    os.makedirs(results_dir, exist_ok=True)
    csv_filename = os.path.join(results_dir, f'twitter_scraper_results_til_{end_date_str}.csv')
    
    # Create a dictionary to consolidate keywords per URL
    url_data = {}  # {(profile, url): {'keywords': set(), 'content': str, 'date': str}}
    
    for profile, kwdata in results.items():
        for keyword, urls in kwdata.items():
            for url in urls:  # urls are already deduplicated from sets
                key = (profile, url)
                if key not in url_data:
                    tweet_content = all_tweet_contents.get(url, "Content not available")
                    tweet_date = all_tweet_dates.get(url, "Unknown")
                    cleaned_content = " ".join(tweet_content.split())
                    url_data[key] = {
                        'keywords': set(),
                        'content': cleaned_content,
                        'date': tweet_date
                    }
                url_data[key]['keywords'].add(keyword)
    
    # Convert to CSV rows with consolidated keywords
    csv_rows = []
    for (profile, url), data in url_data.items():
        # Join keywords with comma and space
        keywords_str = ", ".join(sorted(data['keywords']))
        csv_rows.append([profile, keywords_str, data['date'], url, data['content']])
    
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Profile', 'Keywords', 'Date', 'Tweet URL', 'Tweet Content'])
        writer.writerows(csv_rows)  # Write all consolidated rows
    print(f"\n💾 Results exported to CSV: {csv_filename}")
    print("📋 You can open this CSV in Excel or Google Sheets.")
