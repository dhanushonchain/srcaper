# import asyncio
# import json
# import csv
# import os
# import random
# from datetime import datetime, timezone
# from playwright.async_api import async_playwright
# import re
# from urllib.parse import urlparse
# from dateutil import parser as date_parser

# # Load environment variables from .env file (for future use)
# try:
#     from dotenv import load_dotenv
#     # Load .env from the config directory relative to this script
#     env_path = os.path.join(os.path.dirname(__file__), '..', 'config', '.env.date-scraper')
#     load_dotenv(env_path)
# except ImportError:
#     # If python-d    result = await extractor.extract_single_tweet(tweet_id)
#     if result:
#         print(f"📅 Date: {result['date']}")
#         print(f"👤 Author: {result['author']}")
#         print(f"📝 Text: {result['tweet_text']}")
#         print(f"👁️ Views: {result['views']}")
#         print(f"📊 Status: {result['status']}")
    
#     return results not available, continue without env loading
#     pass

# class TwitterDateExtractor:
#     def __init__(self, headless=True, delay=2000):
#         self.headless = headless
#         self.delay = delay
#         self.results = []
        
#         # Load settings from environment variables
#         self.delay_min = int(os.environ.get('SCRAPER_DELAY_MIN', '2000'))
#         self.delay_max = int(os.environ.get('SCRAPER_DELAY_MAX', '5000'))
#         self.retry_attempts = int(os.environ.get('SCRAPER_RETRY_ATTEMPTS', '3'))
#         self.retry_delay = int(os.environ.get('SCRAPER_RETRY_DELAY', '5000'))
        
#         # Twitter credentials
#         self.username = os.environ.get('TWITTER_USERNAME')
#         self.password = os.environ.get('TWITTER_PASSWORD')
#         self.email = os.environ.get('TWITTER_EMAIL')
        
#         # User agents for rotation
#         self.user_agents = [
#             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
#             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
#             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
#             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
#             "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
#         ]
    
#     async def _login_to_twitter(self, page):
#         """Login to Twitter/X using credentials"""
#         if not all([self.username, self.password]):
#             print("⚠️ No Twitter credentials provided, proceeding without login...")
#             return False
            
#         try:
#             print("🔐 Attempting to login to Twitter/X...")
#             await page.goto("https://x.com/login", wait_until="domcontentloaded")
#             await page.wait_for_timeout(3000)
            
#             # Enter username
#             username_input = await page.wait_for_selector('input[name="text"]', timeout=10000)
#             await username_input.fill(self.username)
#             await page.click('text=Next')
#             await page.wait_for_timeout(2000)
            
#             # Check if email verification is needed
#             try:
#                 email_input = await page.wait_for_selector('input[name="text"]', timeout=5000)
#                 if email_input and self.email:
#                     print("📧 Email verification required...")
#                     await email_input.fill(self.email)
#                     await page.click('text=Next')
#                     await page.wait_for_timeout(2000)
#             except:
#                 pass  # Email verification not needed
            
#             # Enter password
#             password_input = await page.wait_for_selector('input[name="password"]', timeout=10000)
#             await password_input.fill(self.password)
#             await page.click('text=Log in')
#             await page.wait_for_timeout(5000)
            
#             # Check if login was successful
#             try:
#                 await page.wait_for_selector('[aria-label="Account menu"]', timeout=15000)
#                 print("✅ Successfully logged in to Twitter/X")
#                 return True
#             except:
#                 print("❌ Login may have failed or requires additional verification")
#                 return False
                
#         except Exception as e:
#             print(f"❌ Login error: {str(e)}")
#             return False
#     async def extract_dates(self, json_file_path, output_file_path="tweet_dates.csv"):
#         """Main extraction method"""
#         tweet_links = self._load_tweet_links(json_file_path)
#         if not tweet_links:
#             return []
        
#         async with async_playwright() as p:
#             # Use random user agent
#             user_agent = random.choice(self.user_agents)
#             print(f"🌐 Using user agent: {user_agent[:50]}...")
            
#             browser = await p.chromium.launch(headless=self.headless)
#             context = await browser.new_context(user_agent=user_agent)
#             page = await context.new_page()
            
#             # Attempt login
#             login_success = await self._login_to_twitter(page)
            
#             for i, tweet_url in enumerate(tweet_links, 1):
#                 success = await self._process_tweet_with_retry(page, tweet_url, i, len(tweet_links))
                
#                 # Random delay between requests
#                 delay = random.randint(self.delay_min, self.delay_max)
#                 print(f"⏱️ Waiting {delay/1000:.1f}s before next request...")
#                 await page.wait_for_timeout(delay)
            
#             await browser.close()
        
#         self._save_results(output_file_path)
#         return self.results
    
#     def _load_tweet_links(self, json_file_path):
#         """Load and validate tweet links from JSON file"""
#         try:
#             with open(json_file_path, 'r', encoding='utf-8') as file:
#                 links = json.load(file)
            
#             # Validate URLs
#             valid_links = []
#             for link in links:
#                 if self._is_valid_twitter_url(link):
#                     valid_links.append(link)
#                 else:
#                     print(f"⚠️  Invalid Twitter URL skipped: {link}")
            
#             return valid_links
#         except Exception as e:
#             print(f"Error loading JSON file: {e}")
#             return []
    
#     def _is_valid_twitter_url(self, url):
#         """Validate if URL is a Twitter/X URL"""
#         try:
#             parsed = urlparse(url)
#             return parsed.netloc in ['twitter.com', 'x.com'] and '/status/' in parsed.path
#         except:
#             return False
    
#     async def _process_tweet_with_retry(self, page, tweet_url, current, total):
#         """Process tweet with retry mechanism"""
#         for attempt in range(1, self.retry_attempts + 1):
#             try:
#                 success = await self._process_tweet(page, tweet_url, current, total, attempt)
#                 if success:
#                     return True
                    
#                 if attempt < self.retry_attempts:
#                     print(f"🔄 Retry {attempt}/{self.retry_attempts} failed, waiting {self.retry_delay/1000:.1f}s...")
#                     await page.wait_for_timeout(self.retry_delay)
                    
#             except Exception as e:
#                 if attempt < self.retry_attempts:
#                     print(f"🔄 Attempt {attempt} failed: {str(e)}, retrying...")
#                     await page.wait_for_timeout(self.retry_delay)
#                 else:
#                     print(f"❌ All retry attempts failed for {tweet_url}")
#                     return False
        
#         return False
#     async def _process_tweet(self, page, tweet_url, current, total, attempt=1):
#         """Process individual tweet"""
#         attempt_str = f" (attempt {attempt})" if attempt > 1 else ""
#         print(f"[{current}/{total}] Processing{attempt_str}: {tweet_url}")
        
#         try:
#             await page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
#             await page.wait_for_timeout(4000)  # Increased wait time
            
#             # Check if we hit a login wall or access restriction
#             page_content = await page.content()
#             page_title = await page.title()
            
#             if "Don't miss what's happening" in page_content or "Log in" in page_title:
#                 result = {
#                     'tweet_url': tweet_url,
#                     'date': 'Login required',
#                     'author': 'Access restricted',
#                     'tweet_text': 'Tweet requires login to view',
#                     'views': 'Access restricted',
#                     'extraction_time': datetime.now(timezone.utc).isoformat(),
#                     'status': 'restricted'
#                 }
#                 self.results.append(result)
#                 print(f"⚠️ Restricted: Login required")
#                 return False  # Indicate failure for retry
            
#             # Extract date
#             date_info = await self._extract_date(page)
#             # Format date to YYYY-MM-DD
#             formatted_date = self._format_date(date_info)
            
#             # Extract additional info
#             tweet_text = await self._extract_tweet_text(page)
#             author = await self._extract_author(page)
#             views = await self._extract_views(page)
            
#             result = {
#                 'tweet_url': tweet_url,
#                 'date': formatted_date,
#                 'author': author,
#                 'tweet_text': tweet_text[:200] + "..." if len(tweet_text) > 200 else tweet_text,
#                 'views': views,
#                 'extraction_time': datetime.now(timezone.utc).isoformat(),
#                 'status': 'success' if date_info not in ['Not found', 'Login required'] else 'failed'
#             }
            
#             self.results.append(result)
#             print(f"✅ Success: Date={date_info}, Views={views}")
#             return True  # Indicate success
            
#         except Exception as e:
#             print(f"❌ Error: {str(e)}")
#             # Don't append error result here, let retry mechanism handle it
#             if attempt >= self.retry_attempts:
#                 self.results.append({
#                     'tweet_url': tweet_url,
#                     'date': 'Error',
#                     'author': 'Error',
#                     'tweet_text': f'Error after {self.retry_attempts} attempts: {str(e)}',
#                     'views': 'Error',
#                     'extraction_time': datetime.now(timezone.utc).isoformat(),
#                     'status': 'error'
#                 })
#             return False  # Indicate failure for retry
    
#     async def _extract_date(self, page):
#         """Extract tweet date using multiple strategies"""
#         # Wait for content to load
#         await page.wait_for_timeout(2000)
        
#         # Enhanced selectors for different Twitter layouts
#         selectors = [
#             'time[datetime]',
#             '[data-testid="Time"] time[datetime]',
#             '[data-testid="Time"] time',
#             'article time[datetime]',
#             'article time',
#             'time',
#             '[datetime]',
#             # Alternative selectors for different layouts
#             '[data-testid="tweet"] time',
#             '.css-1dbjc4n time',
#             'main time[datetime]'
#         ]
        
#         for selector in selectors:
#             try:
#                 element = await page.query_selector(selector)
#                 if element:
#                     # Try datetime attribute first
#                     datetime_attr = await element.get_attribute('datetime')
#                     if datetime_attr:
#                         return datetime_attr
                    
#                     # Try title attribute (sometimes contains full date)
#                     title_attr = await element.get_attribute('title')
#                     if title_attr:
#                         return title_attr
                    
#                     # Try text content
#                     text_content = await element.text_content()
#                     if text_content and text_content.strip():
#                         return text_content.strip()
#             except Exception as e:
#                 continue
        
#         # Try to extract from page title or meta tags as fallback
#         try:
#             page_title = await page.title()
#             if "Don't miss what's happening" in page_title:
#                 return "Access restricted - Login required"
#         except:
#             pass
            
#         return 'Not found'
    
#     async def _extract_tweet_text(self, page):
#         """Extract tweet text content"""
#         selectors = [
#             '[data-testid="tweetText"]',
#             '[lang] span',
#             '.tweet-text'
#         ]
        
#         for selector in selectors:
#             try:
#                 element = await page.query_selector(selector)
#                 if element:
#                     text = await element.text_content()
#                     return text.strip() if text else 'No text found'
#             except:
#                 continue
        
#         return 'No text found'
    
#     async def _extract_author(self, page):
#         """Extract tweet author"""
#         selectors = [
#             '[data-testid="User-Names"] span',
#             '.username',
#             '[href*="/"]'
#         ]
        
#         for selector in selectors:
#             try:
#                 element = await page.query_selector(selector)
#                 if element:
#                     text = await element.text_content()
#                     if text and '@' in text:
#                         return text.strip()
#             except:
#                 continue
        
#         return 'Unknown'
    
#     async def _extract_views(self, page):
#         """Extract tweet view count"""
#         view_selectors = [
#             '[data-testid="app-text-transition-container"] span',  # New X.com layout
#             '[data-testid="socialContext"] span',  # Alternative layout
#             '[aria-label*="view"] span',  # Views with aria-label
#             '[data-testid="analytics"] span',  # Analytics section
#             'span[data-testid="app-text-transition-container"]',  # Direct span selector
#             'a[href*="/analytics"] span',  # Analytics link
#             '[role="group"] span:contains("view")',  # Group containing views
#         ]
        
#         for selector in view_selectors:
#             try:
#                 # Handle different possible layouts
#                 elements = await page.query_selector_all(selector)
#                 for element in elements:
#                     text = await element.text_content()
#                     if text and self._is_view_count(text.strip()):
#                         return self._parse_view_count(text.strip())
#             except Exception as e:
#                 continue
        
#         # Try extracting from analytics section specifically
#         try:
#             # Look for analytics or stats section
#             analytics_section = await page.query_selector('[data-testid="analytics"]')
#             if analytics_section:
#                 spans = await analytics_section.query_selector_all('span')
#                 for span in spans:
#                     text = await span.text_content()
#                     if text and self._is_view_count(text.strip()):
#                         return self._parse_view_count(text.strip())
#         except:
#             pass
        
#         # Try looking for view patterns in all text content
#         try:
#             # Get all spans and look for view patterns
#             all_spans = await page.query_selector_all('span')
#             for span in all_spans:
#                 text = await span.text_content()
#                 if text and self._is_view_count(text.strip()):
#                     return self._parse_view_count(text.strip())
#         except:
#             pass
        
#         return 'Not found'
    
#     def _is_view_count(self, text):
#         """Check if text contains view count pattern"""
#         if not text:
#             return False
        
#         text_lower = text.lower()
        
#         # Common view patterns
#         view_patterns = [
#             r'\d+[\.,]?\d*\s*views?',  # "123 views", "1.2K views"
#             r'\d+[\.,]?\d*[km]?\s*views?',  # "123K views", "1.2M views" 
#             r'\d+[\.,]?\d*[km]?$',  # Just numbers with K/M suffix
#         ]
        
#         for pattern in view_patterns:
#             if re.search(pattern, text_lower):
#                 return True
        
#         # Check for numeric patterns that might be views (but be careful of other metrics)
#         if re.match(r'^\d+[\.,]?\d*[km]?$', text_lower):
#             # Could be views, but we need more context
#             return True
            
#         return False
    
#     def _parse_view_count(self, text):
#         """Parse view count from text"""
#         if not text:
#             return 'Not found'
        
#         # Remove "views" text and clean
#         cleaned = re.sub(r'\s*views?\s*', '', text.lower()).strip()
        
#         # Handle K, M suffixes
#         if cleaned.endswith('k'):
#             try:
#                 num = float(cleaned[:-1].replace(',', '.'))
#                 return f"{int(num * 1000)}"
#             except:
#                 return cleaned
#         elif cleaned.endswith('m'):
#             try:
#                 num = float(cleaned[:-1].replace(',', '.'))
#                 return f"{int(num * 1000000)}"
#             except:
#                 return cleaned
#         elif cleaned.replace(',', '').replace('.', '').isdigit():
#             return cleaned.replace(',', '')
        
#         return text  # Return original if can't parse
    
#     def _save_results(self, output_file_path):
#         """Save results to CSV file"""
#         if not self.results:
#             print("No results to save")
#             return
        
#         # Ensure output directory exists
#         os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
#         with open(output_file_path, 'w', newline='', encoding='utf-8') as csvfile:
#             fieldnames = ['tweet_url', 'date', 'author', 'tweet_text', 'views', 'extraction_time', 'status']
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#             writer.writeheader()
#             writer.writerows(self.results)
        
#         successful = sum(1 for r in self.results if r['status'] == 'success')
#         print(f"\n✓ Results saved to '{output_file_path}'")
#         print(f"📊 Success rate: {successful}/{len(self.results)} tweets")

#     async def extract_single_tweet(self, tweet_id_or_url, output_file_path=None):
#         """Extract date from a single tweet ID or URL with enhanced features"""
#         # Convert to URL if needed
#         tweet_url = self._convert_to_url(tweet_id_or_url)
#         if not tweet_url:
#             print(f"❌ Invalid tweet ID/URL: {tweet_id_or_url}")
#             return None
        
#         async with async_playwright() as p:
#             # Use random user agent
#             user_agent = random.choice(self.user_agents)
#             print(f"🌐 Using user agent: {user_agent[:50]}...")
            
#             browser = await p.chromium.launch(headless=self.headless)
#             context = await browser.new_context(user_agent=user_agent)
#             page = await context.new_page()
            
#             # Attempt login
#             login_success = await self._login_to_twitter(page)
            
#             # Process tweet with retry
#             success = await self._process_tweet_with_retry(page, tweet_url, 1, 1)
#             await browser.close()
        
#         if output_file_path:
#             self._save_results(output_file_path)
        
#         return self.results[0] if self.results else None

#     def _convert_to_url(self, item):
#         """Convert tweet ID or URL to full URL"""
#         try:
#             # If it's already a full URL, validate it
#             if item.startswith(('http://', 'https://')):
#                 if self._is_valid_twitter_url(item):
#                     return item
#                 return None
            
#             # If it's just numbers, treat as tweet ID
#             if item.isdigit():
#                 return f"https://x.com/i/status/{item}"
            
#             # If it's in format /status/123456, convert to full URL
#             if item.startswith('/status/') and item.split('/')[-1].isdigit():
#                 return f"https://x.com{item}"
            
#             # If it's in format username/status/123456, convert to full URL
#             if '/status/' in item and item.split('/')[-1].isdigit():
#                 return f"https://x.com/{item}"
            
#             return None
#         except:
#             return None

# # Usage examples
# async def run_extraction():
#     """Extract dates from multiple tweets using JSON file"""
#     # Use data/input for input files and data/output for output files
#     input_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'input', 'tweet_links.json')
#     output_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'output', 'tweet_dates_output.csv')
    
#     # Enhanced extractor with authentication and retry
#     extractor = TwitterDateExtractor(headless=True, delay=2000)
#     results = await extractor.extract_dates(input_file, output_file)
#     return results

# async def extract_single_tweet_example():
#     """Extract date from a single tweet using just the ID with enhanced features"""
#     extractor = TwitterDateExtractor(headless=True, delay=1000)
    
#     # You can use any of these formats:
#     tweet_id = "1967337132659532232"  # Just the ID
#     # tweet_url = "https://x.com/username/status/1967337132659532232"  # Full URL
#     # tweet_path = "/status/1967337132659532232"  # Path only
    
#     result = await extractor.extract_single_tweet(tweet_id)
#         if result:
#             print(f"📅 Date: {result['date']}")
#             print(f"👤 Author: {result['author']}")
#             print(f"📝 Text: {result['tweet_text']}")
#             print(f"�️ Views: {result['views']}")
#             print(f"�📊 Status: {result['status']}")    return result

# # Run the script
# if __name__ == "__main__":
#     import sys
    
#     if len(sys.argv) > 1:
#         # Single tweet mode: python date-scraper.py TWEET_ID
#         tweet_id = sys.argv[1]
#         print(f"🔍 Extracting date for tweet: {tweet_id}")
#         print("🚀 Enhanced scraper with login, retry, and user agent rotation")
        
#         async def single_tweet_run():
#             extractor = TwitterDateExtractor(headless=True, delay=1000)
#             result = await extractor.extract_single_tweet(tweet_id)
#             if result:
#                 print(f"\n📊 Final Results:")
#                 print(f"📅 Date: {result['date']}")
#                 print(f"👤 Author: {result['author']}")
#                 print(f"📝 Text: {result['tweet_text']}")
#                 print(f"🏷️ Status: {result['status']}")
#             return result
        
#         asyncio.run(single_tweet_run())
#     else:
#         # Batch mode: python date-scraper.py (uses JSON file)
#         print("📋 Running batch extraction from JSON file...")
#         print("🚀 Enhanced scraper with login, retry, and user agent rotation")
#         asyncio.run(run_extraction())
