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

# Load environment variables from .env file (for future use)
try:
    from dotenv import load_dotenv
    # Load .env from the config directory relative to this script
    env_path = os.path.join(os.path.dirname(__file__), '..', 'config', '.env.date-scraper')
    load_dotenv(env_path)
except ImportError:
    # If python-dotenv is not available, continue without env loading
    pass

class TwitterDateExtractor:
    def __init__(self, headless=True, delay=2000):
        self.headless = headless
        self.delay = delay
        self.results = []
        
        # Load settings from environment variables
        self.delay_min = int(os.environ.get('SCRAPER_DELAY_MIN', '2000'))
        self.delay_max = int(os.environ.get('SCRAPER_DELAY_MAX', '5000'))
        self.retry_attempts = int(os.environ.get('SCRAPER_RETRY_ATTEMPTS', '3'))
        self.retry_delay = int(os.environ.get('SCRAPER_RETRY_DELAY', '5000'))
        
        # Twitter credentials
        self.username = os.environ.get('TWITTER_USERNAME')
        self.password = os.environ.get('TWITTER_PASSWORD')
        self.email = os.environ.get('TWITTER_EMAIL')
        
        # User agents for rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        ]
    
    async def _login_to_twitter(self, page):
        """Login to Twitter/X using credentials"""
        if not all([self.username, self.password]):
            print("⚠️ No Twitter credentials provided, proceeding without login...")
            return False
            
        try:
            print("🔐 Attempting to login to Twitter/X...")
            await page.goto("https://x.com/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            # Enter username
            username_input = await page.wait_for_selector('input[name="text"]', timeout=10000)
            await username_input.fill(self.username)
            await page.click('text=Next')
            await page.wait_for_timeout(2000)
            
            # Check if email verification is needed
            try:
                email_input = await page.wait_for_selector('input[name="text"]', timeout=5000)
                if email_input and self.email:
                    print("📧 Email verification required...")
                    await email_input.fill(self.email)
                    await page.click('text=Next')
                    await page.wait_for_timeout(2000)
            except:
                pass  # Email verification not needed
            
            # Enter password
            password_input = await page.wait_for_selector('input[name="password"]', timeout=10000)
            await password_input.fill(self.password)
            await page.click('text=Log in')
            await page.wait_for_timeout(5000)
            
            # Check if login was successful
            try:
                await page.wait_for_selector('[aria-label="Account menu"]', timeout=15000)
                print("✅ Successfully logged in to Twitter/X")
                return True
            except:
                print("❌ Login may have failed or requires additional verification")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False

    async def extract_dates(self, json_file_path, output_file_path="tweet_dates.csv"):
        """Main extraction method"""
        tweet_links = self._load_tweet_links(json_file_path)
        if not tweet_links:
            return []
        
        async with async_playwright() as p:
            # Use random user agent
            user_agent = random.choice(self.user_agents)
            print(f"🌐 Using user agent: {user_agent[:50]}...")
            
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            
            # Attempt login
            login_success = await self._login_to_twitter(page)
            
            for i, tweet_url in enumerate(tweet_links, 1):
                success = await self._process_tweet_with_retry(page, tweet_url, i, len(tweet_links))
                
                # Random delay between requests
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
            
            # Validate URLs
            valid_links = []
            for link in links:
                if self._is_valid_twitter_url(link):
                    valid_links.append(link)
                else:
                    print(f"⚠️  Invalid Twitter URL skipped: {link}")
            
            return valid_links
        except Exception as e:
            print(f"Error loading JSON file: {e}")
            return []
    
    def _is_valid_twitter_url(self, url):
        """Validate if URL is a Twitter/X URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc in ['twitter.com', 'x.com'] and '/status/' in parsed.path
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
                    print(f"🔄 Retry {attempt}/{self.retry_attempts} failed, waiting {self.retry_delay/1000:.1f}s...")
                    await page.wait_for_timeout(self.retry_delay)
                    
            except Exception as e:
                if attempt < self.retry_attempts:
                    print(f"🔄 Attempt {attempt} failed: {str(e)}, retrying...")
                    await page.wait_for_timeout(self.retry_delay)
                else:
                    print(f"❌ All retry attempts failed for {tweet_url}")
                    return False
        
        return False

    async def _process_tweet(self, page, tweet_url, current, total, attempt=1):
        """Process individual tweet using XHR interception (FREE web scraping)"""
        attempt_str = f" (attempt {attempt})" if attempt > 1 else ""
        print(f"[{current}/{total}] Processing{attempt_str}: {tweet_url}")
        
        # Storage for captured background requests
        xhr_data = []
        
        async def capture_xhr(response):
            """Capture background API calls that Twitter makes"""
            try:
                # Twitter's internal API endpoint for tweet data
                if "TweetResultByRestId" in response.url or "TweetDetail" in response.url:
                    data = await response.json()
                    xhr_data.append(data)
                    print(f"  ✓ Captured XHR data from {response.url[:80]}...")
            except Exception as e:
                pass  # Ignore non-JSON responses
        
        try:
            # Enable XHR capture BEFORE loading page
            page.on("response", capture_xhr)
            
            await page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8000)  # Extended wait for background requests to complete
            
            # Check for login wall
            page_content = await page.content()
            page_title = await page.title()
            
            if "Don't miss what's happening" in page_content or "Log in" in page_title:
                result = {
                    'tweet_url': tweet_url,
                    'date': 'Login required',
                    'views': 'Access restricted',
                    'extraction_time': datetime.now(timezone.utc).isoformat(),
                    'status': 'restricted'
                }
                self.results.append(result)
                print(f"⚠️ Restricted: Login required")
                return False
            
            # Try XHR data first (95%+ reliable)
            if xhr_data:
                print(f"  📦 Processing {len(xhr_data)} XHR responses...")
                extracted = self._parse_xhr_data(xhr_data[0])
                
                if extracted:
                    result = {
                        'tweet_url': tweet_url,
                        'date': extracted['date'],
                        'views': extracted['views'],
                        'extraction_time': datetime.now(timezone.utc).isoformat(),
                        'status': 'success'
                    }
                    self.results.append(result)
                    print(f"✅ XHR Success: Date={extracted['date']}, Views={extracted['views']}")
                    return True
            
            # Fallback to HTML parsing if XHR didn't work
            print("⚠️ XHR data not found, falling back to HTML parsing...")
            date_info = await self._extract_date(page)
            formatted_date = self._format_date(date_info)
            views = await self._extract_views_accurate(page)  # Use more accurate method
            
            result = {
                'tweet_url': tweet_url,
                'date': formatted_date,
                'views': views,
                'extraction_time': datetime.now(timezone.utc).isoformat(),
                'status': 'success' if formatted_date not in ['Not found', 'Error'] else 'failed'
            }
            
            self.results.append(result)
            print(f"✅ HTML Success: Date={formatted_date}, Views={views}")
            return True
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            if attempt >= self.retry_attempts:
                self.results.append({
                    'tweet_url': tweet_url,
                    'date': 'Error',
                    'views': 'Error',
                    'extraction_time': datetime.now(timezone.utc).isoformat(),
                    'status': 'error'
                })
            return False  # Indicate failure for retry
    
    async def _extract_date(self, page):
        """Extract tweet date using multiple strategies"""
        # Wait for content to load
        await page.wait_for_timeout(2000)
        
        # Enhanced selectors for different Twitter layouts
        selectors = [
            'time[datetime]',
            '[data-testid="Time"] time[datetime]',
            '[data-testid="Time"] time',
            'article time[datetime]',
            'article time',
            'time',
            '[datetime]',
            # Alternative selectors for different layouts
            '[data-testid="tweet"] time',
            '.css-1dbjc4n time',
            'main time[datetime]'
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # Try datetime attribute first
                    datetime_attr = await element.get_attribute('datetime')
                    if datetime_attr:
                        return datetime_attr
                    
                    # Try title attribute (sometimes contains full date)
                    title_attr = await element.get_attribute('title')
                    if title_attr:
                        return title_attr
                    
                    # Try text content
                    text_content = await element.text_content()
                    if text_content and text_content.strip():
                        return text_content.strip()
            except Exception as e:
                continue
        
        # Try to extract from page title or meta tags as fallback
        try:
            page_title = await page.title()
            if "Don't miss what's happening" in page_title:
                return "Access restricted - Login required"
        except:
            pass
            
        return 'Not found'
    
    async def _extract_tweet_text(self, page):
        """Extract tweet text content"""
        selectors = [
            '[data-testid="tweetText"]',
            '[lang] span',
            '.tweet-text'
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    return text.strip() if text else 'No text found'
            except:
                continue
        
        return 'No text found'
    
    async def _extract_author(self, page):
        """Extract tweet author"""
        selectors = [
            '[data-testid="User-Names"] span',
            '.username',
            '[href*="/"]'
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text and '@' in text:
                        return text.strip()
            except:
                continue
        
        return 'Unknown'
    
    def _format_date(self, date_str):
        """Format date string to YYYY-MM-DD format"""
        if not date_str or date_str in ['Not found', 'Login required', 'Access restricted', 'Error']:
            return date_str
        
        try:
            # Parse the date string (handles various formats including ISO)
            parsed_date = date_parser.parse(date_str)
            # Return in YYYY-MM-DD format
            return parsed_date.strftime('%Y-%m-%d')
        except Exception as e:
            # If parsing fails, return original string
            print(f"⚠️ Could not parse date '{date_str}': {e}")
            return date_str
    
    def _parse_xhr_data(self, xhr_response):
        """Parse tweet data from captured background requests (FREE)"""
        try:
            # Navigate Twitter's JSON structure
            tweet_result = xhr_response.get('data', {}).get('tweetResult', {}).get('result', {})
            
            if not tweet_result:
                # Try alternative path
                tweet_result = xhr_response.get('data', {}).get('threaded_conversation_with_injections_v2', {})
                if tweet_result:
                    instructions = tweet_result.get('instructions', [])
                    for instruction in instructions:
                        if instruction.get('type') == 'TimelineAddEntries':
                            entries = instruction.get('entries', [])
                            for entry in entries:
                                content = entry.get('content', {})
                                item_content = content.get('itemContent', {})
                                if item_content:
                                    tweet_result = item_content.get('tweet_results', {}).get('result', {})
                                    break
            
            if not tweet_result:
                print("  ⚠️ No tweet result found in XHR data")
                return None
            
            # Extract legacy data (contains most info)
            legacy = tweet_result.get('legacy', {})
            
            # Get views data
            views_data = tweet_result.get('views', {})
            view_count = views_data.get('count', 'Not found')
            
            # Format view count
            if isinstance(view_count, (int, str)) and str(view_count).replace(',', '').isdigit():
                view_count = self._format_number(int(str(view_count).replace(',', '')))
            
            # Get created date
            created_at = legacy.get('created_at', 'Not found')
            formatted_date = self._format_date(created_at)
            
            print(f"  📊 XHR extracted: Date={formatted_date}, Views={view_count}")
            
            return {
                'date': formatted_date,
                'views': view_count
            }
            
        except Exception as e:
            print(f"  ⚠️ Error parsing XHR data: {e}")
            return None
    
    def _format_number(self, num):
        """Format large numbers with K/M/B suffixes"""
        if not isinstance(num, (int, float)):
            return str(num)
        
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        else:
            return str(int(num))
    
    async def _extract_views(self, page):
        """Extract tweet view count"""
        print("🔍 Looking for view count...")
        
        # Wait a bit more for analytics to load
        await page.wait_for_timeout(3000)
        
        view_selectors = [
            # Primary selectors for view count
            '[data-testid="app-text-transition-container"] span',  # New X.com layout
            '[data-testid="socialContext"] span',  # Alternative layout
            '[aria-label*="view"] span',  # Views with aria-label
            '[data-testid="analytics"] span',  # Analytics section
            'span[data-testid="app-text-transition-container"]',  # Direct span selector
            'a[href*="/analytics"] span',  # Analytics link
            # More specific selectors
            '[role="group"] span',  # Group containing views
            '[data-testid="tweet"] [role="group"] span',  # Tweet group
            'article [role="group"] span',  # Article group
        ]
        
        for selector in view_selectors:
            try:
                print(f"  Trying selector: {selector}")
                elements = await page.query_selector_all(selector)
                print(f"  Found {len(elements)} elements")
                
                for i, element in enumerate(elements):
                    text = await element.text_content()
                    if text:
                        text = text.strip()
                        print(f"    Element {i}: '{text}'")
                        if self._is_view_count(text):
                            view_count = self._parse_view_count(text)
                            print(f"✅ Found views: {view_count}")
                            return view_count
            except Exception as e:
                print(f"  Error with selector {selector}: {e}")
                continue
        
        # Try extracting from analytics section specifically
        try:
            print("  Trying analytics section...")
            analytics_section = await page.query_selector('[data-testid="analytics"]')
            if analytics_section:
                spans = await analytics_section.query_selector_all('span')
                print(f"  Found {len(spans)} spans in analytics")
                for i, span in enumerate(spans):
                    text = await span.text_content()
                    if text:
                        text = text.strip()
                        print(f"    Analytics span {i}: '{text}'")
                        if self._is_view_count(text):
                            view_count = self._parse_view_count(text)
                            print(f"✅ Found views in analytics: {view_count}")
                            return view_count
        except Exception as e:
            print(f"  Error in analytics section: {e}")
        
        # Try looking for view patterns in all text content as last resort
        try:
            print("  Searching all spans for view patterns...")
            all_spans = await page.query_selector_all('span')
            print(f"  Found {len(all_spans)} total spans")
            
            view_candidates = []
            for i, span in enumerate(all_spans):
                text = await span.text_content()
                if text:
                    text = text.strip()
                    if self._is_view_count(text):
                        view_candidates.append(text)
                        print(f"    Candidate {len(view_candidates)}: '{text}'")
            
            if view_candidates:
                # Return the first candidate that looks like a view count
                view_count = self._parse_view_count(view_candidates[0])
                print(f"✅ Found views from candidates: {view_count}")
                return view_count
                
        except Exception as e:
            print(f"  Error in full search: {e}")
        
        print("❌ Views not found")
        return 'Not found'
    
    async def _extract_views_accurate(self, page):
        """More accurate view extraction using correct selectors"""
        print("🎯 Using accurate view extraction...")
        
        # Wait longer for views to load
        await page.wait_for_timeout(5000)
        
        # The most accurate selector for view counts
        accurate_selectors = [
            'a[aria-label$="Views. View Tweet analytics"]',  # Primary accurate selector
            'a[href*="/analytics"]',  # Analytics link
            '[data-testid="app-text-transition-container"]',  # Transition container
        ]
        
        for selector in accurate_selectors:
            try:
                print(f"  🎯 Trying accurate selector: {selector}")
                element = await page.query_selector(selector)
                
                if element:
                    # Try aria-label first (most reliable)
                    aria_label = await element.get_attribute('aria-label')
                    if aria_label and 'Views' in aria_label:
                        # Extract number from "12.3K Views. View Tweet analytics"
                        view_part = aria_label.split(' Views')[0]
                        if view_part:
                            parsed_views = self._parse_view_count(view_part)
                            print(f"✅ Found views via aria-label: {parsed_views}")
                            return parsed_views
                    
                    # Try text content
                    text = await element.text_content()
                    if text and self._is_view_count(text.strip()):
                        parsed_views = self._parse_view_count(text.strip())
                        print(f"✅ Found views via text: {parsed_views}")
                        return parsed_views
                        
            except Exception as e:
                print(f"  Error with accurate selector {selector}: {e}")
                continue
        
        # Final fallback - look for any element containing view patterns
        try:
            print("  🔍 Final search for view patterns...")
            all_elements = await page.query_selector_all('*')
            
            for element in all_elements:
                aria_label = await element.get_attribute('aria-label')
                if aria_label and ('view' in aria_label.lower() or 'Views' in aria_label):
                    if any(char.isdigit() for char in aria_label):
                        # Extract the number part
                        import re
                        numbers = re.findall(r'[\d,\.]+[KMB]?', aria_label)
                        if numbers:
                            view_candidate = numbers[0]
                            if self._is_view_count(view_candidate + ' views'):
                                parsed_views = self._parse_view_count(view_candidate)
                                print(f"✅ Found views in aria-label: {parsed_views}")
                                return parsed_views
                                
        except Exception as e:
            print(f"  Error in final search: {e}")
        
        print("❌ Accurate view extraction failed")
        return 'Not found'
    
    def _is_view_count(self, text):
        """Check if text contains view count pattern"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Common view patterns
        view_patterns = [
            r'\d+[\.,]?\d*\s*views?',  # "123 views", "1.2K views"
            r'\d+[\.,]?\d*[km]?\s*views?',  # "123K views", "1.2M views" 
        ]
        
        for pattern in view_patterns:
            if re.search(pattern, text_lower):
                return True
        
        # Check for numeric patterns that might be views (but be more selective)
        # Only consider it if it's a standalone number with K/M or larger than 100
        if re.match(r'^\d+[\.,]?\d*[km]$', text_lower):
            return True
        elif re.match(r'^\d+$', text) and len(text) >= 3:  # At least 3 digits
            # Could be views if it's a reasonable number
            try:
                num = int(text.replace(',', ''))
                return num >= 100  # Views are usually 100+
            except:
                return False
            
        return False
    
    def _parse_view_count(self, text):
        """Parse view count from text"""
        if not text:
            return 'Not found'
        
        # Remove "views" text and clean
        cleaned = re.sub(r'\s*views?\s*', '', text.lower()).strip()
        
        # Handle K, M suffixes
        if cleaned.endswith('k'):
            try:
                num = float(cleaned[:-1].replace(',', '.'))
                return f"{int(num * 1000)}"
            except:
                return cleaned
        elif cleaned.endswith('m'):
            try:
                num = float(cleaned[:-1].replace(',', '.'))
                return f"{int(num * 1000000)}"
            except:
                return cleaned
        elif cleaned.replace(',', '').replace('.', '').isdigit():
            return cleaned.replace(',', '')
        
        return text  # Return original if can't parse
    
    def _save_results(self, output_file_path):
        """Save results to CSV file"""
        if not self.results:
            print("No results to save")
            return
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
        with open(output_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['tweet link', 'date', 'views']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Transform results to match the requested format
            simplified_results = []
            for result in self.results:
                simplified_results.append({
                    'tweet link': result['tweet_url'],
                    'date': result['date'],
                    'views': result['views']
                })
            
            writer.writerows(simplified_results)
        
        successful = sum(1 for r in self.results if r['status'] == 'success')
        with_views = sum(1 for r in self.results if r.get('views', 'Not found') not in ['Not found', 'Error', 'Access restricted'])
        
        print(f"\n✓ Results saved to '{output_file_path}'")
        print(f"📊 Success rate: {successful}/{len(self.results)} tweets")
        print(f"👁️ Views found: {with_views}/{len(self.results)} tweets")

    async def extract_single_tweet(self, tweet_id_or_url, output_file_path=None):
        """Extract date from a single tweet ID or URL with enhanced features"""
        # Convert to URL if needed
        tweet_url = self._convert_to_url(tweet_id_or_url)
        if not tweet_url:
            print(f"❌ Invalid tweet ID/URL: {tweet_id_or_url}")
            return None
        
        async with async_playwright() as p:
            # Use random user agent
            user_agent = random.choice(self.user_agents)
            print(f"🌐 Using user agent: {user_agent[:50]}...")
            
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            
            # Attempt login
            login_success = await self._login_to_twitter(page)
            
            # Process tweet with retry
            success = await self._process_tweet_with_retry(page, tweet_url, 1, 1)
            await browser.close()
        
        if output_file_path:
            self._save_results(output_file_path)
        
        return self.results[0] if self.results else None

    def _convert_to_url(self, item):
        """Convert tweet ID or URL to full URL"""
        try:
            # If it's already a full URL, validate it
            if item.startswith(('http://', 'https://')):
                if self._is_valid_twitter_url(item):
                    return item
                return None
            
            # If it's just numbers, treat as tweet ID
            if item.isdigit():
                return f"https://x.com/i/status/{item}"
            
            # If it's in format /status/123456, convert to full URL
            if item.startswith('/status/') and item.split('/')[-1].isdigit():
                return f"https://x.com{item}"
            
            # If it's in format username/status/123456, convert to full URL
            if '/status/' in item and item.split('/')[-1].isdigit():
                return f"https://x.com/{item}"
            
            return None
        except:
            return None

# Usage examples
async def run_extraction():
    """Extract dates from multiple tweets using JSON file"""
    # Use data/input for input files and data/output for output files
    input_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'input', 'tweet_links.json')
    output_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'output', 'tweet_dates_with_views.csv')
    
    # Enhanced extractor with authentication and retry
    extractor = TwitterDateExtractor(headless=True, delay=2000)
    results = await extractor.extract_dates(input_file, output_file)
    return results

async def extract_single_tweet_example():
    """Extract date and views from a single tweet using just the ID with enhanced features"""
    extractor = TwitterDateExtractor(headless=True, delay=1000)
    
    # You can use any of these formats:
    tweet_id = "1967337132659532232"  # Just the ID
    # tweet_url = "https://x.com/username/status/1967337132659532232"  # Full URL
    # tweet_path = "/status/1967337132659532232"  # Path only
    
    result = await extractor.extract_single_tweet(tweet_id)
    if result:
        print(f"📅 Date: {result['date']}")
        print(f"👤 Author: {result['author']}")
        print(f"📝 Text: {result['tweet_text']}")
        print(f"👁️ Views: {result['views']}")
        print(f"📊 Status: {result['status']}")
    
    return result

# Run the script
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Single tweet mode: python date-scraper-with-views.py TWEET_ID
        tweet_id = sys.argv[1]
        print(f"🔍 Extracting date and views for tweet: {tweet_id}")
        print("🚀 Enhanced scraper with login, retry, user agent rotation, and view count extraction")
        
        async def single_tweet_run():
            extractor = TwitterDateExtractor(headless=True, delay=1000)
            result = await extractor.extract_single_tweet(tweet_id)
            if result:
                print(f"\n📊 Final Results:")
                print(f"📅 Date: {result['date']}")
                print(f"️ Views: {result['views']}")
                print(f"🏷️ Status: {result['status']}")
            return result
        
        asyncio.run(single_tweet_run())
    else:
        # Batch mode: python date-scraper-with-views.py (uses JSON file)
        print("📋 Running batch extraction from JSON file...")
        print("🚀 Enhanced scraper with login, retry, user agent rotation, and view count extraction")
        asyncio.run(run_extraction())