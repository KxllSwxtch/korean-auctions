"""
Base Models for All Auction Services

Provides standardized error types and response models for consistent
error handling across all auction implementations.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AuctionErrorType(str, Enum):
    """
    Standardized error types for all auctions.

    Use these in error responses to enable consistent error handling
    across frontend and backend.
    """

    # Authentication errors
    AUTHENTICATION_FAILED = "authentication_failed"
    SESSION_EXPIRED = "session_expired"

    # Data errors
    CAR_NOT_FOUND = "car_not_found"
    NO_DATA_AVAILABLE = "no_data_available"

    # Parsing errors
    PARSING_FAILED = "parsing_failed"
    PARTIAL_PARSING = "partial_parsing"
    INVALID_HTML_STRUCTURE = "invalid_html_structure"

    # Network errors
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"

    # Redirect errors
    UNEXPECTED_REDIRECT = "redirect"
    LOGIN_REDIRECT = "login_redirect"

    # Validation errors
    VALIDATION_ERROR = "validation_error"
    INVALID_PARAMETERS = "invalid_parameters"

    # Rate limiting
    RATE_LIMITED = "rate_limited"
    TOO_MANY_REQUESTS = "too_many_requests"

    # Unknown
    UNKNOWN_ERROR = "unknown_error"


class BaseErrorResponse(BaseModel):
    """
    Base error response model for all auctions.

    Provides consistent error structure across all auction endpoints.
    """

    success: bool = Field(False, description="Always False for error responses")
    message: str = Field(..., description="Human-readable error message")
    error_type: Optional[AuctionErrorType] = Field(
        None,
        description="Machine-readable error type for client-side handling"
    )
    missing_fields: Optional[List[str]] = Field(
        None,
        description="List of fields that failed to extract (for parsing errors)"
    )
    extraction_stats: Optional[Dict[str, bool]] = Field(
        None,
        description="Per-field extraction success status (for parsing errors)"
    )
    timestamp: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp of when error occurred"
    )

    class Config:
        populate_by_name = True


class BaseDetailResponse(BaseModel):
    """
    Base detail response model for all auctions.

    Provides consistent response structure for car detail endpoints.
    """

    success: bool = Field(True, description="Whether operation was successful")
    message: Optional[str] = Field(None, description="Success or error message")
    source_url: Optional[str] = Field(None, description="Source URL of the data")
    error_type: Optional[AuctionErrorType] = Field(
        None,
        description="Error type if success=False"
    )
    missing_fields: Optional[List[str]] = Field(
        None,
        description="Missing fields if parsing was incomplete"
    )
    extraction_stats: Optional[Dict[str, bool]] = Field(
        None,
        description="Per-field extraction statistics"
    )

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


def get_http_status_for_error(error_type: AuctionErrorType) -> int:
    """
    Get appropriate HTTP status code for error type.

    This ensures consistent HTTP status codes across all auction endpoints.

    Args:
        error_type: The error type

    Returns:
        HTTP status code (401, 404, 500, etc.)

    Example:
        status = get_http_status_for_error(AuctionErrorType.CAR_NOT_FOUND)
        # Returns: 404
    """
    error_to_status = {
        # 401 Unauthorized
        AuctionErrorType.AUTHENTICATION_FAILED: 401,
        AuctionErrorType.SESSION_EXPIRED: 401,

        # 404 Not Found
        AuctionErrorType.CAR_NOT_FOUND: 404,
        AuctionErrorType.NO_DATA_AVAILABLE: 404,
        AuctionErrorType.UNEXPECTED_REDIRECT: 404,
        AuctionErrorType.LOGIN_REDIRECT: 404,

        # 400 Bad Request
        AuctionErrorType.VALIDATION_ERROR: 400,
        AuctionErrorType.INVALID_PARAMETERS: 400,

        # 429 Too Many Requests
        AuctionErrorType.RATE_LIMITED: 429,
        AuctionErrorType.TOO_MANY_REQUESTS: 429,

        # 500 Internal Server Error
        AuctionErrorType.PARSING_FAILED: 500,
        AuctionErrorType.INVALID_HTML_STRUCTURE: 500,
        AuctionErrorType.UNKNOWN_ERROR: 500,

        # 502 Bad Gateway
        AuctionErrorType.HTTP_ERROR: 502,
        AuctionErrorType.PARTIAL_PARSING: 502,

        # 503 Service Unavailable
        AuctionErrorType.NETWORK_ERROR: 503,

        # 504 Gateway Timeout
        AuctionErrorType.TIMEOUT: 504,
    }

    return error_to_status.get(error_type, 500)


def create_error_response(
    error_type: AuctionErrorType,
    message: str,
    missing_fields: Optional[List[str]] = None,
    extraction_stats: Optional[Dict[str, bool]] = None
) -> BaseErrorResponse:
    """
    Create standardized error response.

    Args:
        error_type: Type of error
        message: Human-readable error message
        missing_fields: Optional list of missing fields
        extraction_stats: Optional extraction statistics

    Returns:
        BaseErrorResponse with all fields populated

    Example:
        error = create_error_response(
            AuctionErrorType.CAR_NOT_FOUND,
            "Car CA12345 not found in auction",
            missing_fields=["car_name", "price"]
        )
    """
    from datetime import datetime

    return BaseErrorResponse(
        success=False,
        message=message,
        error_type=error_type,
        missing_fields=missing_fields,
        extraction_stats=extraction_stats,
        timestamp=datetime.now().isoformat()
    )
