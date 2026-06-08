#!/usr/bin/env python3
"""Greenhouse Applicant Automation Script

Automates filling out Greenhouse job application forms for Observe.AI and other employers.
Supports --dry-run mode to validate config without submitting.

Usage:
    python greenhouse_applicant.py --job-id 5220940008 --role "Senior CSM" --dry-run
    python greenhouse_applicant.py --job-id 5220940008 --role "Senior CSM" --submit
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Load .env file manually (no python-dotenv dependency)
def load_env(env_path: str = ".env") -> dict:
    """Load environment variables from .env file."""
    env_vars = {}
    path = Path(env_path)
    if not path.exists():
        print(f"WARNING: {env_path} not found. Using system env vars only.")
        return env_vars
    
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def validate_config(env: dict) -> list[str]:
    """Validate that all required config is present. Returns list of errors."""
    errors = []
    
    required_fields = [
        "OBSERVE_AI_SECURITY_CODE",
        "USER_FIRST_NAME",
        "USER_LAST_NAME", 
        "USER_EMAIL",
        "USER_COUNTRY"
    ]
    
    for field in required_fields:
        if not env.get(field):
            errors.append(f"Missing required config: {field}")
    
    # Check resume path exists (optional but recommended)
    resume_path = env.get("RESUME_PATH")
    if resume_path and not Path(resume_path).exists():
        print(f"WARNING: Resume file not found at {resume_path}")
    
    return errors


def dry_run(env: dict, job_id: str, role: str):
    """Validate configuration without submitting anything."""
    print("=" * 60)
    print("DRY RUN MODE - Validating configuration...")
    print("=" * 60)
    
    errors = validate_config(env)
    
    if errors:
        print("\n❌ Configuration errors found:")
        for error in errors:
            print(f"   • {error}")
        return False
    
    print("\n✅ All required configuration present!")
    print("\n📋 Config Summary:")
    print(f"   First Name:     {env['USER_FIRST_NAME']}")
    print(f"   Last Name:      {env['USER_LAST_NAME']}")
    print(f"   Email:          {env['USER_EMAIL']}")
    print(f"   Country:        {env['USER_COUNTRY']}")
    print(f"   Phone:          {env.get('USER_PHONE', 'Not set')}")
    print(f"\n🎯 Target Job:")
    print(f"   Job ID:         {job_id}")
    print(f"   Role:           {role}")
    
    # Check browser availability
    try:
        from playwright.sync_api import sync_playwright
        print("\n✅ Playwright is installed and available!")
        
        # Quick browser launch test
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.observe.ai/careers", timeout=10000)
            print(f"✅ Successfully loaded Observe.AI careers page")
            print(f"   Page title: {page.title()}")
            browser.close()
            
    except ImportError:
        print("\n⚠️  Playwright not installed. Install with:")
        print("   pip install playwright")
        print("   playwright install chromium")
        return False
    except Exception as e:
        print(f"\n⚠️  Browser test failed: {e}")
        print("   This is OK for dry-run - just means browser automation may need setup.")
    
    print("\n" + "=" * 60)
    print("✅ DRY RUN PASSED! Ready to submit applications.")
    print("=" * 60)
    return True


def submit_application(env: dict, job_id: str, role: str):
    """Submit application using browser automation."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright not installed. Run:")
        print("  pip install playwright")
        print("  playwright install chromium")
        sys.exit(1)
    
    security_code = env["OBSERVE_AI_SECURITY_CODE"]
    base_url = f"https://boards.greenhouse.io/embed/job_board?for=observeai&validityToken={security_code}"
    
    print(f"\n🚀 Starting application submission for {role} (Job ID: {job_id})...")
    print(f"   Browser timeout: {env.get('BROWSER_TIMEOUT', '30')}s")
    print(f"   Headless mode: {'ON' if env.get('HEADLESS') == 'true' else 'OFF'}\n")
    
    with sync_playwright() as p:
        headless = env.get("HEADLESS", "false").lower() == "true"
        browser = p.chromium.launch(headless=headless)
        
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()
            
            # Navigate to Greenhouse job board
            print("📡 Loading Observe.AI careers page...")
            page.goto(base_url, timeout=30000)
            print(f"   ✅ Page loaded: {page.title()}")
            
            # Find and click "Apply" for the target role
            print(f"\n🔍 Looking for '{role}' position...")
            
            # Wait for page to load
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # Try to find the apply button - this will vary by job board layout
            apply_selectors = [
                f'button:has-text("{role}")',
                f'a:has-text("{role}")',
                'button:has-text("Apply")',
                '.job-card a',
                '.js-job-link'
            ]
            
            applied = False
            for selector in apply_selectors:
                try:
                    element = page.query_selector(selector)
                    if element and element.is_visible():
                        print(f"   ✅ Found element matching '{selector}'")
                        element.click()
                        applied = True
                        break
                except Exception as e:
                    continue
            
            if not applied:
                print("   ⚠️  Could not auto-find apply button. Manual intervention may be needed.")
                print(f"   Please navigate to the job and click 'Apply' manually.")
                print(f"\n   Direct URL:")
                print(f"   {base_url}")
                return False
            
            # Wait for application form to load
            print("\n⏳ Waiting for application form...")
            page.wait_for_timeout(5000)
            
            # Fill in basic fields
            print("📝 Filling application form...")
            
            fields = {
                "#first_name, input[name='first_name'], [id*='first_name']": env["USER_FIRST_NAME"],
                "#last_name, input[name='last_name'], [id*='last_name']": env["USER_LAST_NAME"],
                "#email, input[name='email'], [id*='email']": env["USER_EMAIL"],
                "#country, input[name='country'], [id*='country']": env["USER_COUNTRY"]
            }
            
            for selector, value in fields.items():
                try:
                    element = page.query_selector(selector)
                    if element and element.is_visible():
                        element.fill(value)
                        print(f"   ✅ Filled: {selector.split(',')[0].strip()}")
                except Exception as e:
                    print(f"   ⚠️  Could not fill {selector}: {e}")
            
            # Resume upload (if file exists)
            resume_path = env.get("RESUME_PATH")
            if resume_path and Path(resume_path).exists():
                try:
                    file_input = page.query_selector('input[type="file"][id*="resume"], input[name*="resume"]')
                    if file_input:
                        file_input.set_input_files(resume_path)
                        print(f"   ✅ Resume uploaded from {resume_path}")
                except Exception as e:
                    print(f"   ⚠️  Could not upload resume: {e}")
            
            # Submit the form
            print("\n📤 Attempting to submit application...")
            try:
                submit_btn = page.query_selector('button[type="submit"], input[type="submit"]')
                if submit_btn and submit_btn.is_visible():
                    submit_btn.click()
                    page.wait_for_timeout(5000)
                    
                    # Check for success message
                    success_selectors = [
                        '.success-message',
                        '[class*="success"]',
                        'h1:has-text("Thank you")',
                        'h2:has-text("Application received")'
                    ]
                    
                    submitted = False
                    for selector in success_selectors:
                        try:
                            if page.query_selector(selector):
                                print(f"   ✅ Application submitted successfully!")
                                submitted = True
                                break
                        except:
                            continue
                    
                    if not submitted:
                        print("   ⚠️  Submission status unclear. Check the browser window.")
                else:
                    print("   ⚠️  No submit button found. Form may need manual completion.")
            except Exception as e:
                print(f"   ❌ Submit failed: {e}")
            
        finally:
            browser.close()
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Greenhouse Applicant Automation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to validate config
  python greenhouse_applicant.py --job-id 5220940008 --role "Senior CSM" --dry-run
  
  # Submit application (opens browser)
  python greenhouse_applicant.py --job-id 5220940008 --role "Senior CSM" --submit
        """
    )
    
    parser.add_argument("--job-id", required=True, help="Greenhouse job ID")
    parser.add_argument("--role", required=True, help="Job title/role name")
    parser.add_argument("--dry-run", action="store_true", help="Validate config without submitting")
    parser.add_argument("--submit", action="store_true", help="Submit application via browser")
    parser.add_argument("--env-file", default=".env", help="Path to .env file (default: .env)")
    
    args = parser.parse_args()
    
    # Load environment variables
    env = load_env(args.env_file)
    
    if args.dry_run:
        success = dry_run(env, args.job_id, args.role)
        sys.exit(0 if success else 1)
    
    elif args.submit:
        errors = validate_config(env)
        if errors:
            print("❌ Cannot submit with configuration errors:")
            for error in errors:
                print(f"   • {error}")
            sys.exit(1)
        
        success = submit_application(env, args.job_id, args.role)
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        print("\n⚠️  Please specify --dry-run or --submit")
        sys.exit(1)


if __name__ == "__main__":
    main()
