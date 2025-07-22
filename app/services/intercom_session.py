"""
Intercom session management for PLC Auction
"""
import time
import uuid
import logging
import threading
from typing import Dict, Optional, Any
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class IntercomSession:
    """Manages Intercom session for PLC Auction"""
    
    PING_URL = "https://api-iam.intercom.io/messenger/web/ping"
    PING_INTERVAL = 30  # seconds
    
    def __init__(self):
        self.app_id = "m1d5ih1o"
        self.anonymous_id = "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6"
        self.device_identifier = "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa"
        self.session_id = "8446c849-be9c-46cf-ae3e-163460f53146"
        self.idempotency_key = None
        self.last_ping = None
        self.ping_thread = None
        self.should_ping = False
        self.user_id = None
        
    def start_ping_loop(self):
        """Start background ping loop"""
        if self.ping_thread and self.ping_thread.is_alive():
            logger.warning("Ping loop already running")
            return
            
        self.should_ping = True
        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self.ping_thread.start()
        logger.info("🏓 Started Intercom ping loop")
        
    def stop_ping_loop(self):
        """Stop background ping loop"""
        self.should_ping = False
        if self.ping_thread:
            self.ping_thread.join(timeout=5)
        logger.info("🛑 Stopped Intercom ping loop")
        
    def _ping_loop(self):
        """Background ping loop"""
        while self.should_ping:
            try:
                self.ping()
                time.sleep(self.PING_INTERVAL)
            except Exception as e:
                logger.error(f"Error in ping loop: {e}")
                time.sleep(5)  # Wait before retry
                
    def generate_idempotency_key(self) -> str:
        """Generate new idempotency key"""
        return uuid.uuid4().hex[:16]
        
    def ping(self, referer: str = "https://plc.auction/auction") -> Optional[Dict[str, Any]]:
        """
        Send ping to Intercom to maintain session
        
        Args:
            referer: The referer URL
            
        Returns:
            Response data or None if failed
        """
        try:
            # Generate new idempotency key for each ping
            self.idempotency_key = self.generate_idempotency_key()
            
            headers = {
                "accept": "*/*",
                "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://plc.auction",
                "priority": "u=1, i",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
                "sec-fetch-storage-access": "active",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            }
            
            data = {
                "app_id": self.app_id,
                "v": "3",
                "g": "792c1eab01c0e85d9f858ecffb583407f7c332e0",
                "s": self.session_id,
                "r": "https://plc.auction/",
                "platform": "web",
                "installation_type": "js-snippet",
                "installation_version": "undefined",
                "Idempotency-Key": self.idempotency_key,
                "internal": "{}",
                "is_intersection_booted": "false",
                "page_title": "PLC auction Auto - Cars auction – PLC Auction",
                "user_active_company_id": "undefined",
                "user_data": f'{{"anonymous_id":"{self.anonymous_id}"}}',
                "source": "apiBoot",
                "sampling": "false",
                "referer": referer,
                "device_identifier": self.device_identifier,
            }
            
            response = requests.post(self.PING_URL, headers=headers, data=data, timeout=10)
            
            if response.status_code == 200:
                self.last_ping = datetime.now()
                response_data = response.json()
                
                # Extract user ID if available
                if 'user' in response_data and 'id' in response_data['user']:
                    self.user_id = response_data['user']['id']
                    
                logger.info(f"✅ Intercom ping successful (user_id: {self.user_id})")
                return response_data
            else:
                logger.error(f"❌ Intercom ping failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error sending Intercom ping: {e}")
            return None
            
    def get_intercom_cookies(self) -> Dict[str, str]:
        """
        Get Intercom-related cookies
        
        Returns:
            Dictionary of Intercom cookies
        """
        return {
            "intercom-id-m1d5ih1o": self.anonymous_id,
            "intercom-device-id-m1d5ih1o": self.device_identifier,
            "intercom-session-m1d5ih1o": "",  # Empty as per the example
        }