"""
Base Parser for All Auction Scrapers

Provides common functionality for robust HTML parsing with fallback selectors,
extraction statistics, and error handling.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, Any
from loguru import logger


class BaseAuctionParser(ABC):
    """
    Abstract base class for auction parsers with built-in robustness features.

    Features:
    - Fallback selector system for resilient parsing
    - Extraction statistics tracking
    - Missing fields detection
    - Debug HTML saving
    - Standardized error handling

    Subclasses should:
    1. Define SELECTOR_FALLBACKS dict
    2. Implement parse methods
    3. Call _track_extraction() for each field
    """

    # Subclasses should override this with their specific selectors
    SELECTOR_FALLBACKS: Dict[str, List[Tuple[str, str, Optional[str]]]] = {}

    def __init__(self, name: str):
        """
        Initialize parser with name for logging

        Args:
            name: Parser name for logging (e.g., "Lotte Parser")
        """
        self.name = name
        self.extraction_stats: Dict[str, bool] = {}
        logger.info(f"🔧 {self.name} инициализирован")

    def _find_with_fallbacks(
        self,
        soup: Any,
        field_name: str,
        log_success: bool = True
    ) -> Optional[Any]:
        """
        Try to find element using multiple fallback selectors.

        This method tries each selector in SELECTOR_FALLBACKS[field_name] until
        one succeeds. This makes parsing resilient to HTML structure changes.

        Args:
            soup: BeautifulSoup object
            field_name: Name of field to find (must exist in SELECTOR_FALLBACKS)
            log_success: Whether to log successful finds (default True)

        Returns:
            Found element or None

        Example:
            SELECTOR_FALLBACKS = {
                "car_name": [
                    ("td", "ttable_tit", "차명"),
                    ("td", "ttable-tit", "차명"),
                    ("span", "car-name", None),
                ]
            }

            element = self._find_with_fallbacks(soup, "car_name")
        """
        fallbacks = self.SELECTOR_FALLBACKS.get(field_name, [])

        if not fallbacks:
            logger.warning(
                f"⚠️ {self.name}: No fallbacks configured for field '{field_name}'"
            )
            return None

        for idx, (tag, css_class, text) in enumerate(fallbacks):
            try:
                if text:
                    # Search by tag, class, and text content
                    element = soup.find(
                        tag,
                        class_=css_class,
                        string=lambda s: text in s.strip() if s else False
                    )
                else:
                    # Search only by tag and class
                    element = soup.find(tag, class_=css_class)

                if element:
                    if log_success:
                        logger.debug(
                            f"✅ {self.name}: Found '{field_name}' using fallback #{idx+1}: "
                            f"{tag}.{css_class}" + (f" with text '{text}'" if text else "")
                        )
                    return element

            except Exception as e:
                logger.debug(
                    f"⚠️ {self.name}: Fallback #{idx+1} failed for '{field_name}': {e}"
                )
                continue

        logger.warning(
            f"⚠️ {self.name}: Failed to find '{field_name}' with all {len(fallbacks)} fallback(s)"
        )
        return None

    def _track_extraction(self, field_name: str, value: Any) -> None:
        """
        Track whether a field was successfully extracted.

        Args:
            field_name: Name of the field
            value: Extracted value (truthy = success, falsy = failure)
        """
        self.extraction_stats[field_name] = bool(value)

    def _get_missing_fields(
        self,
        critical_fields: List[str]
    ) -> Tuple[List[str], bool]:
        """
        Get list of missing critical fields and overall success status.

        Args:
            critical_fields: List of field names that MUST be extracted

        Returns:
            Tuple of (missing_fields_list, has_all_critical_data)

        Example:
            missing, success = self._get_missing_fields([
                "car_name", "price", "image"
            ])
            if not success:
                logger.error(f"Missing: {missing}")
        """
        missing_fields = [
            field for field in critical_fields
            if not self.extraction_stats.get(field, False)
        ]
        has_all_critical = len(missing_fields) == 0

        return missing_fields, has_all_critical

    def _save_debug_html(
        self,
        html_content: str,
        identifier: str,
        reason: str = "parsing_failed"
    ) -> Optional[str]:
        """
        Save HTML to debug file for later analysis.

        Args:
            html_content: HTML string to save
            identifier: Unique identifier (e.g., car_id)
            reason: Reason for saving (e.g., "parsing_failed", "empty_data")

        Returns:
            Path to saved file or None if save failed
        """
        try:
            import os
            from datetime import datetime

            # Create debug directory
            debug_dir = "debug_html"
            os.makedirs(debug_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            parser_name = self.name.lower().replace(" ", "_")
            filename = f"{debug_dir}/{parser_name}_{reason}_{identifier}_{timestamp}.html"

            # Save HTML
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info(f"💾 {self.name}: HTML saved for debugging: {filename}")
            return filename

        except Exception as e:
            logger.warning(
                f"⚠️ {self.name}: Failed to save debug HTML: {e}"
            )
            return None

    def _reset_stats(self) -> None:
        """Reset extraction statistics for new parse operation."""
        self.extraction_stats = {}

    def _get_extraction_summary(self) -> Dict[str, Any]:
        """
        Get summary of extraction statistics.

        Returns:
            Dict with extracted, failed, and total counts
        """
        extracted = [k for k, v in self.extraction_stats.items() if v]
        failed = [k for k, v in self.extraction_stats.items() if not v]

        return {
            "total_fields": len(self.extraction_stats),
            "extracted_count": len(extracted),
            "failed_count": len(failed),
            "extracted_fields": extracted,
            "failed_fields": failed,
            "success_rate": (
                len(extracted) / len(self.extraction_stats) * 100
                if self.extraction_stats else 0
            )
        }

    @abstractmethod
    def parse(self, *args, **kwargs) -> Any:
        """
        Main parse method - must be implemented by subclasses.

        Subclasses should:
        1. Call _reset_stats() at start
        2. Use _find_with_fallbacks() for extraction
        3. Call _track_extraction() for each field
        4. Use _get_missing_fields() for validation
        5. Call _save_debug_html() on failure
        """
        pass
