import asyncio
import json
import csv
import os
import random
from datetime import datetime, timezone
from playwright.async_api import async_playwright
import re
from urllib.parse import urlparse
from dateutil import parser as date_parser

try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', 'config', '.env.date-scraper')
    load_dotenv(env_path)
except ImportError:
    pass

class TwitterDateExtractor:
    def __init__(self, headless=True, delay=2000):
        self.headless = headless
        self.delay = delay
        self.results = []
        
        # Increase wait times for better reliability
        self.delay_min = int(os.environ.get('SCRAPER_DELAY_MIN', '3000'))  # Increased from 2000
        self.delay_max = int(os.environ.get('SCRAPER_DELAY_MAX', '6000'))  # Increased from 5000
        self.retry_attempts = int(os.environ.get('SCRAPER_RETRY_ATTEMPTS', '3'))
        self.retry_delay = int(os.environ.get('SCRAPER_RETRY_DELAY', '5000'))
        
        # Twitter credentials
        self.username = os.environ.get('TWITTER_USERNAME')
        self.password = os.environ.get('TWITTER_PASSWORD')
        self.email = os.environ.get('TWITTER_EMAIL')
        
        # User agents for rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        # Track XHR responses
        self.xhr_responses = []
    
    async def _login_to_twitter(self, page):
        """Improved login with better error handling"""
        if not all([self.username, self.password]):
            print("⚠️ No Twitter credentials provided, proceeding without login...")
            return False
            
        try:
            print("🔐 Attempting to login to Twitter/X...")
            await page.goto("https://x.com/login", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Enter username
            username_input = await page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            await username_input.click()
            await username_input.fill(self.username)
            await page.wait_for_timeout(1000)
            
            # Click next button
            next_button = await page.wait_for_selector('button:has-text("Next")', timeout=5000)
            await next_button.click()
            await page.wait_for_timeout(3000)
            
            # Check for unusual activity / email verification
            try:
                email_check = await page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=3000)
                if email_check and self.email:
                    print("📧 Email verification required...")
                    await email_check.fill(self.email)
                    verify_button = await page.wait_for_selector('button:has-text("Next")')
                    await verify_button.click()
                    await page.wait_for_timeout(2000)
            except:
                pass  # No email verification needed
            
            # Enter password
            password_input = await page.wait_for_selector('input[name="password"]', timeout=10000)
            await password_input.click()
            await password_input.fill(self.password)
            await page.wait_for_timeout(1000)
            
            # Click login button
            login_button = await page.wait_for_selector('button[data-testid="LoginForm_Login_Button"]', timeout=5000)
            await login_button.click()
            await page.wait_for_timeout(5000)
            
            # Verify login success
            try:
                await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=15000)
                print("✅ Successfully logged in to Twitter/X")
                return True
            except:
                # Alternative check
                current_url = page.url
                if "home" in current_url or "x.com/" in current_url:
                    print("✅ Login appears successful (URL check)")
                    return True
                print("❌ Login verification failed")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False

    async def extract_dates(self, json_file_path, output_file_path="tweet_dates.csv"):
        """Main extraction method with improved error handling"""
        tweet_links = self._load_tweet_links(json_file_path)
        if not tweet_links:
            print("❌ No valid tweet links found")
            return []
        
        print(f"📊 Found {len(tweet_links)} tweets to process")
        
        async with async_playwright() as p:
            user_agent = random.choice(self.user_agents)
            print(f"🌐 Using user agent: {user_agent[:50]}...")
            
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            
            page = await context.new_page()
            
            # Set longer timeout
            context.set_default_timeout(60000)
            
            # Attempt login
            login_success = await self._login_to_twitter(page)
            if not login_success:
                print("⚠️ Continuing without login - may have limited data access")
            
            # Process each tweet
            for i, tweet_url in enumerate(tweet_links, 1):
                print(f"\n{'='*60}")
                success = await self._process_tweet_with_retry(page, tweet_url, i, len(tweet_links))
                
                # Random delay between requests
                if i < len(tweet_links):  # Don't delay after last tweet
                    delay = random.randint(self.delay_min, self.delay_max)
                    print(f"⏱️ Waiting {delay/1000:.1f}s before next request...")
                    await page.wait_for_timeout(delay)
            
            await browser.close()
        
        self._save_results(output_file_path)
        return self.results
    
    def _load_tweet_links(self, json_file_path):
        """Load and validate tweet links from JSON file"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as file:
                links = json.load(file)
            
            if not isinstance(links, list):
                print(f"❌ JSON file must contain an array of URLs")
                return []
            
            valid_links = []
            for link in links:
                if self._is_valid_twitter_url(link):
                    valid_links.append(link)
                else:
                    print(f"⚠️ Invalid Twitter URL skipped: {link}")
            
            return valid_links
        except FileNotFoundError:
            print(f"❌ File not found: {json_file_path}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON format: {e}")
            return []
        except Exception as e:
            print(f"❌ Error loading JSON file: {e}")
            return []
    
    def _is_valid_twitter_url(self, url):
        """Validate if URL is a Twitter/X URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc in ['twitter.com', 'x.com', 'www.twitter.com', 'www.x.com'] and '/status/' in parsed.path
        except:
            return False
    
    async def _process_tweet_with_retry(self, page, tweet_url, current, total):
        """Process tweet with retry mechanism"""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                success = await self._process_tweet(page, tweet_url, current, total, attempt)
                if success:
                    return True
                    
                if attempt < self.retry_attempts:
                    print(f"🔄 Retry {attempt}/{self.retry_attempts} - waiting {self.retry_delay/1000:.1f}s...")
                    await page.wait_for_timeout(self.retry_delay)
                    
            except Exception as e:
                print(f"❌ Attempt {attempt} error: {str(e)}")
                if attempt < self.retry_attempts:
                    await page.wait_for_timeout(self.retry_delay)
                else:
                    print(f"❌ All {self.retry_attempts} attempts failed for {tweet_url}")
                    self.results.append({
                        'tweet_url': tweet_url,
                        'date': 'Error',
                        'views': 'Error',
                        'extraction_time': datetime.now(timezone.utc).isoformat(),
                        'status': 'error'
                    })
                    return False
        
        return False

    async def _process_tweet(self, page, tweet_url, current, total, attempt=1):
        """Improved tweet processing with better XHR capture"""
        attempt_str = f" (attempt {attempt})" if attempt > 1 else ""
        print(f"[{current}/{total}] Processing{attempt_str}: {tweet_url}")
        
        # Clear previous XHR data
        self.xhr_responses = []
        
        async def capture_response(response):
            """Capture API responses"""
            try:
                url = response.url
                # Capture relevant API endpoints
                if any(endpoint in url for endpoint in ['TweetResultByRestId', 'TweetDetail', 'graphql']):
                    if response.status == 200:
                        try:
                            data = await response.json()
                            self.xhr_responses.append(data)
                            print(f"  ✓ Captured API response from {url[:80]}...")
                        except:
                            pass
            except Exception:
                pass
        
        try:
            # Attach response listener BEFORE navigation
            page.on("response", capture_response)
            
            # Navigate to tweet
            print(f"  🌐 Loading tweet page...")
            response = await page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
            
            if not response or response.status != 200:
                print(f"  ⚠️ HTTP {response.status if response else 'No response'}")
            
            # Wait for content to load
            print(f"  ⏳ Waiting for content to fully load...")
            await page.wait_for_timeout(10000)  # Increased wait time
            
            # Try to wait for tweet article
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
                print(f"  ✓ Tweet article loaded")
            except:
                print(f"  ⚠️ Tweet article selector not found")
            
            # Check for access restrictions
            page_content = await page.content()
            page_title = await page.title()
            
            if any(phrase in page_content for phrase in ["Don't miss what's happening", "This Tweet is unavailable", "This Post is unavailable"]):
                result = {
                    'tweet_url': tweet_url,
                    'date': 'Restricted',
                    'views': 'Restricted',
                    'extraction_time': datetime.now(timezone.utc).isoformat(),
                    'status': 'restricted'
                }
                self.results.append(result)
                print(f"⚠️ Tweet is restricted or unavailable")
                return False
            
            # Process XHR data first (most reliable)
            extracted_data = None
            if self.xhr_responses:
                print(f"  📦 Processing {len(self.xhr_responses)} API responses...")
                for xhr_data in self.xhr_responses:
                    extracted_data = self._parse_xhr_data(xhr_data)
                    if extracted_data and extracted_data['date'] != 'Not found':
                        break
            
            # Fallback to HTML parsing if XHR failed
            if not extracted_data or extracted_data['date'] == 'Not found':
                print("  🔍 Falling back to HTML parsing...")
                date_info = await self._extract_date_improved(page)
                views_info = await self._extract_views_improved(page)
                
                extracted_data = {
                    'date': self._format_date(date_info),
                    'views': views_info
                }
            
            # Validate extracted data
            if extracted_data['date'] in ['Not found', 'Error'] and extracted_data['views'] in ['Not found', 'Error']:
                print(f"  ❌ No data extracted, will retry")
                return False
            
            result = {
                'tweet_url': tweet_url,
                'date': extracted_data['date'],
                'views': extracted_data['views'],
                'extraction_time': datetime.now(timezone.utc).isoformat(),
                'status': 'success' if extracted_data['date'] not in ['Not found', 'Error'] else 'partial'
            }
            
            self.results.append(result)
            print(f"✅ Success: Date={result['date']}, Views={result['views']}")
            return True
            
        except Exception as e:
            print(f"❌ Processing error: {str(e)}")
            return False
        finally:
            # Remove listener to prevent memory leaks
            try:
                page.remove_listener("response", capture_response)
            except:
                pass
    
    async def _extract_date_improved(self, page):
        """Improved date extraction"""
        # Wait for time element
        await page.wait_for_timeout(2000)
        
        # Most reliable selectors for date
        selectors = [
            'article[data-testid="tweet"] time[datetime]',
            'time[datetime]',
            '[data-testid="tweet"] time',
        ]
        
        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=5000)
                if element:
                    # Try datetime attribute first (most reliable)
                    datetime_attr = await element.get_attribute('datetime')
                    if datetime_attr:
                        print(f"  ✓ Found date: {datetime_attr}")
                        return datetime_attr
            except:
                continue
        
        print("  ⚠️ Date not found")
        return 'Not found'
    
    async def _extract_views_improved(self, page):
        """Significantly improved view extraction"""
        print("  🔍 Extracting view count...")
        
        # Wait for analytics to load
        await page.wait_for_timeout(3000)
        
        # Strategy 1: Find via aria-label (most reliable)
        try:
            view_link = await page.query_selector('a[href*="/analytics"]')
            if view_link:
                aria_label = await view_link.get_attribute('aria-label')
                if aria_label and 'view' in aria_label.lower():
                    # Extract number from "12.3K Views. View post analytics"
                    match = re.search(r'([\d,\.]+[KMB]?)\s*[Vv]iews?', aria_label)
                    if match:
                        view_count = self._parse_view_count(match.group(1))
                        print(f"  ✓ Found views via aria-label: {view_count}")
                        return view_count
        except Exception as e:
            print(f"  Strategy 1 failed: {e}")
        
        # Strategy 2: Find the analytics group and extract
        try:
            # Look for the group containing view stats
            stats_groups = await page.query_selector_all('[role="group"]')
            for group in stats_groups:
                text = await group.inner_text()
                # Look for view patterns in the group text
                if 'views' in text.lower() or 'view' in text.lower():
                    # Extract number before "views"
                    match = re.search(r'([\d,\.]+[KMB]?)\s*[Vv]iews?', text, re.IGNORECASE)
                    if match:
                        view_count = self._parse_view_count(match.group(1))
                        print(f"  ✓ Found views in stats group: {view_count}")
                        return view_count
        except Exception as e:
            print(f"  Strategy 2 failed: {e}")
        
        # Strategy 3: Find span with data-testid containing view count
        try:
            view_spans = await page.query_selector_all('span[data-testid="app-text-transition-container"]')
            for span in view_spans:
                text = await span.inner_text()
                if text and (text.replace(',', '').replace('.', '').replace('K', '').replace('M', '').replace('B', '').isdigit() or 
                            re.match(r'^\d+[\.,]?\d*[KMB]?$', text)):
                    # Verify this is a view count by checking nearby text
                    parent = await span.evaluate_handle('el => el.parentElement')
                    parent_text = await parent.inner_text() if parent else ''
                    if 'view' in parent_text.lower():
                        view_count = self._parse_view_count(text)
                        print(f"  ✓ Found views in transition container: {view_count}")
                        return view_count
        except Exception as e:
            print(f"  Strategy 3 failed: {e}")
        
        print("  ❌ Views not found")
        return 'Not found'
    
    def _parse_xhr_data(self, xhr_response):
        """Enhanced XHR parsing"""
        try:
            # Navigate Twitter's GraphQL response structure
            data = xhr_response.get('data', {})
            
            # Try multiple paths
            tweet_result = None
            
            # Path 1: tweetResult
            if 'tweetResult' in data:
                tweet_result = data['tweetResult'].get('result', {})
            
            # Path 2: threaded_conversation_with_injections_v2
            if not tweet_result and 'threaded_conversation_with_injections_v2' in data:
                instructions = data['threaded_conversation_with_injections_v2'].get('instructions', [])
                for instruction in instructions:
                    if instruction.get('type') == 'TimelineAddEntries':
                        entries = instruction.get('entries', [])
                        for entry in entries:
                            if 'tweet-' in entry.get('entryId', ''):
                                content = entry.get('content', {})
                                item_content = content.get('itemContent', {})
                                if 'tweet_results' in item_content:
                                    tweet_result = item_content['tweet_results'].get('result', {})
                                    if tweet_result:
                                        break
            
            if not tweet_result:
                return None
            
            # Extract data
            legacy = tweet_result.get('legacy', {})
            views_data = tweet_result.get('views', {})
            
            # Get view count
            view_count = views_data.get('count', 'Not found')
            if isinstance(view_count, str) and view_count.isdigit():
                view_count = int(view_count)
            if isinstance(view_count, int):
                view_count = self._format_number(view_count)
            
            # Get date
            created_at = legacy.get('created_at', 'Not found')
            formatted_date = self._format_date(created_at)
            
            print(f"  📊 XHR data: Date={formatted_date}, Views={view_count}")
            
            return {
                'date': formatted_date,
                'views': view_count
            }
            
        except Exception as e:
            print(f"  ⚠️ XHR parsing error: {e}")
            return None
    
    def _format_number(self, num):
        """Format large numbers"""
        if not isinstance(num, (int, float)):
            return str(num)
        
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        else:
            return f"{int(num):,}"
    
    def _is_view_count(self, text):
        """Check if text contains view count"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Check for explicit "views" text
        if re.search(r'\d+[\.,]?\d*[kmb]?\s*views?', text_lower):
            return True
        
        # Check for numeric patterns
        if re.match(r'^\d+[\.,]?\d*[kmb]?$', text_lower):
            return True
            
        return False
    
    def _parse_view_count(self, text):
        """Parse view count from text"""
        if not text or not isinstance(text, str):
            return 'Not found'
        
        # Clean the text
        cleaned = text.strip().upper()
        
        # Remove "VIEWS" if present
        cleaned = re.sub(r'\s*VIEWS?\s*', '', cleaned, flags=re.IGNORECASE)
        
        # Handle K, M, B suffixes
        multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}
        
        for suffix, multiplier in multipliers.items():
            if cleaned.endswith(suffix):
                try:
                    num_str = cleaned[:-1].replace(',', '.')
                    num = float(num_str)
                    return self._format_number(int(num * multiplier))
                except:
                    return cleaned
        
        # Plain number
        try:
            num = int(cleaned.replace(',', ''))
            return self._format_number(num)
        except:
            return text
    
    def _format_date(self, date_str):
        """Format date string to YYYY-MM-DD"""
        if not date_str or date_str in ['Not found', 'Login required', 'Restricted', 'Error']:
            return date_str
        
        try:
            # Parse and format
            parsed_date = date_parser.parse(date_str)
            return parsed_date.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"  ⚠️ Date parsing failed for '{date_str}': {e}")
            return date_str
    
    def _save_results(self, output_file_path):
        """Save results to CSV"""
        if not self.results:
            print("\n❌ No results to save")
            return
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file_path) if os.path.dirname(output_file_path) else '.', exist_ok=True)
        
        try:
            with open(output_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['tweet link', 'date', 'views']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in self.results:
                    writer.writerow({
                        'tweet link': result['tweet_url'],
                        'date': result['date'],
                        'views': result['views']
                    })
            
            # Statistics
            total = len(self.results)
            successful = sum(1 for r in self.results if r['status'] == 'success')
            with_dates = sum(1 for r in self.results if r['date'] not in ['Not found', 'Error', 'Restricted'])
            with_views = sum(1 for r in self.results if r['views'] not in ['Not found', 'Error', 'Restricted'])
            
            print(f"\n{'='*60}")
            print(f"✅ Results saved to: {output_file_path}")
            print(f"📊 Statistics:")
            print(f"   Total tweets: {total}")
            print(f"   Successful: {successful} ({successful/total*100:.1f}%)")
            print(f"   Dates found: {with_dates} ({with_dates/total*100:.1f}%)")
            print(f"   Views found: {with_views} ({with_views/total*100:.1f}%)")
            print(f"{'='*60}")
            
        except Exception as e:
            print(f"\n❌ Error saving results: {e}")

    def _convert_to_url(self, item):
        """Convert tweet ID or URL to full URL"""
        try:
            if item.startswith(('http://', 'https://')):
                if self._is_valid_twitter_url(item):
                    return item
                return None
            
            if item.isdigit():
                return f"https://x.com/i/status/{item}"
            
            if item.startswith('/status/') and item.split('/')[-1].isdigit():
                return f"https://x.com{item}"
            
            if '/status/' in item and item.split('/')[-1].isdigit():
                return f"https://x.com/{item}"
            
            return None
        except:
            return None

    async def extract_single_tweet(self, tweet_id_or_url, output_file_path=None):
        """Extract data from a single tweet"""
        tweet_url = self._convert_to_url(tweet_id_or_url)
        if not tweet_url:
            print(f"❌ Invalid tweet ID/URL: {tweet_id_or_url}")
            return None
        
        async with async_playwright() as p:
            user_agent = random.choice(self.user_agents)
            
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            context.set_default_timeout(60000)
            
            login_success = await self._login_to_twitter(page)
            success = await self._process_tweet_with_retry(page, tweet_url, 1, 1)
            
            await browser.close()
        
        if output_file_path:
            self._save_results(output_file_path)
        
        return self.results[0] if self.results else None


# Usage functions
async def run_extraction():
    """Batch extraction from JSON file"""
    input_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'input', 'tweet_links.json')
    output_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'output', 'tweet_dates_with_views.csv')
    
    extractor = TwitterDateExtractor(headless=True, delay=2000)
    results = await extractor.extract_dates(input_file, output_file)
    return results


async def extract_single_tweet_example(tweet_id):
    """Single tweet extraction"""
    extractor = TwitterDateExtractor(headless=True, delay=1000)
    result = await extractor.extract_single_tweet(tweet_id)
    
    if result:
        print(f"\n📊 Extracted Data:")
        print(f"   Date: {result['date']}")
        print(f"   Views: {result['views']}")
        print(f"   Status: {result['status']}")
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Single tweet mode
        tweet_id = sys.argv[1]
        print(f"🔍 Extracting data for tweet: {tweet_id}")
        asyncio.run(extract_single_tweet_example(tweet_id))
    else:
        # Batch mode
        print("📋 Running batch extraction from JSON file...")
        asyncio.run(run_extraction())