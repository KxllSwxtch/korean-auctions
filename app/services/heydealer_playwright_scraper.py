"""
HeyDealer Playwright-based scraper for car diagram with markings
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, Browser
import re
import json

logger = logging.getLogger(__name__)


class HeyDealerPlaywrightScraper:
    """Scraper for HeyDealer car details using Playwright"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.base_url = "https://m.heydealer.com"
        
    async def __aenter__(self):
        """Context manager entry"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.cleanup()
        
    async def initialize(self):
        """Initialize Playwright browser"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-gpu',
                    '--window-size=1920,1080',
                ]
            )
            logger.info("Playwright browser initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {e}")
            raise
            
    async def cleanup(self):
        """Cleanup browser resources"""
        try:
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            logger.info("Playwright browser cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            
    async def get_car_diagram_with_markings(self, car_id: str) -> Dict[str, Any]:
        """
        Scrape car diagram with damage markings from HeyDealer
        
        Args:
            car_id: HeyDealer car ID
            
        Returns:
            Dictionary with diagram data and markings
        """
        if not self.browser:
            await self.initialize()
            
        page = await self.browser.new_page()
        
        try:
            # Navigate to car detail page
            url = f"{self.base_url}/cars/{car_id}"
            logger.info(f"Navigating to {url}")
            
            # Set user agent to appear as mobile browser
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            })
            
            response = await page.goto(url, wait_until='networkidle')
            
            if response.status != 200:
                logger.error(f"Failed to load page: {response.status}")
                return self._get_fallback_response(car_id)
                
            # Wait for car diagram section to load
            await page.wait_for_selector('.carsAccidentRepair_76672742', timeout=10000)
            
            # Extract diagram data
            diagram_data = await self._extract_diagram_data(page)
            
            return diagram_data
            
        except Exception as e:
            logger.error(f"Error scraping car {car_id}: {e}")
            return self._get_fallback_response(car_id)
            
        finally:
            await page.close()
            
    async def _extract_diagram_data(self, page: Page) -> Dict[str, Any]:
        """
        Extract diagram data from the page
        
        Args:
            page: Playwright page object
            
        Returns:
            Dictionary with diagram data
        """
        try:
            # Extract diagram image URL
            image_url = await page.eval_on_selector(
                '.accidentRepair_7835d88c img',
                'el => el.src'
            )
            
            # Extract all damage markings
            markings = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('.accidentRepairButton_7f73d312');
                    const markings = [];
                    
                    buttons.forEach(button => {
                        const style = button.getAttribute('style') || '';
                        const transform = style.match(/translate\\((\\d+)px,\\s*(\\d+)px\\)/);
                        
                        if (transform) {
                            const classes = button.className;
                            let repairType = 'none';
                            let label = '';
                            
                            if (classes.includes('weld_0cb92f6e')) {
                                repairType = 'weld';
                                label = 'W';
                            } else if (classes.includes('painted_9b3d16b4')) {
                                repairType = 'painted';
                                label = 'P';
                            } else if (classes.includes('exchange')) {
                                repairType = 'exchange';
                                label = 'E';
                            }
                            
                            markings.push({
                                position: [parseInt(transform[1]), parseInt(transform[2])],
                                repair: repairType,
                                label: label,
                                classes: classes
                            });
                        }
                    });
                    
                    return markings;
                }
            """)
            
            # Get accident summary text
            summary_text = await page.eval_on_selector(
                '.header_b64b8bfd .title_5759b601',
                'el => el.textContent',
                strict=False
            ) or "단순교환 무사고"
            
            # Parse damage counts
            damage_summary = {
                "exchange": 0,
                "weld": 0,
                "painted": 0,
                "none": 0
            }
            
            for marking in markings:
                repair_type = marking.get("repair", "none")
                if repair_type in damage_summary:
                    damage_summary[repair_type] += 1
                    
            # Build response
            result = {
                "success": True,
                "data": {
                    "type": "scraped",
                    "image_url": image_url,
                    "image_width": 420,
                    "accident_summary": summary_text,
                    "accident_repairs": markings,
                    "total_damages": damage_summary["exchange"] + damage_summary["weld"] + damage_summary["painted"],
                    "damage_summary": damage_summary
                },
                "message": "Diagram scraped successfully",
            }
            
            logger.info(f"Successfully extracted {len(markings)} markings")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting diagram data: {e}")
            return self._get_fallback_response("")
            
    def _get_fallback_response(self, car_id: str) -> Dict[str, Any]:
        """
        Get fallback response when scraping fails
        
        Args:
            car_id: Car ID
            
        Returns:
            Fallback response dictionary
        """
        return {
            "success": False,
            "data": {
                "type": None,
                "image_url": "https://heydealer-api.s3.amazonaws.com/static-dj42/img/v2/categorized_accident/dealers/web/accident_repairs_front_panel.fd308c17aee5.png",
                "image_width": 420,
                "accident_repairs": [],
                "total_damages": 0,
                "damage_summary": {
                    "exchange": 0,
                    "weld": 0,
                    "painted": 0,
                    "none": 0
                }
            },
            "message": "Failed to scrape diagram, using fallback"
        }


# Singleton instance
_scraper_instance = None


async def get_scraper() -> HeyDealerPlaywrightScraper:
    """Get or create scraper singleton instance"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = HeyDealerPlaywrightScraper()
        await _scraper_instance.initialize()
    return _scraper_instance


async def scrape_car_diagram(car_id: str) -> Dict[str, Any]:
    """
    Convenience function to scrape car diagram
    
    Args:
        car_id: HeyDealer car ID
        
    Returns:
        Diagram data with markings
    """
    scraper = await get_scraper()
    return await scraper.get_car_diagram_with_markings(car_id)