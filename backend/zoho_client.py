import httpx
import time
from typing import Optional, Dict, Any
from models import ReceiptData, ZohoConfig

class ZohoClient:
    def __init__(self, config: ZohoConfig):
        self.config = config
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        
    async def _refresh_access_token(self):
        """Exchange refresh token for a new access token"""
        accounts_url = f"https://accounts.zoho.{self.config.dc_domain}/oauth/v2/token"
        
        params = {
            "refresh_token": self.config.refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "refresh_token"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(accounts_url, params=params)
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                # Set expiry slightly early to avoid race conditions (usually expires in 3600s)
                self.token_expiry = time.time() + data.get("expires_in", 3600) - 60
                print(f"Zoho Access Token refreshed. Expires in {data.get('expires_in')}s")
            else:
                raise Exception(f"Failed to refresh Zoho token: {response.status_code} - {response.text}")

    async def get_valid_token(self) -> str:
        """Get a valid access token, refreshing if necessary"""
        if not self.access_token or time.time() > self.token_expiry:
            await self._refresh_access_token()
        return self.access_token

    def _map_to_invoice(self, data: ReceiptData) -> Dict[str, Any]:
        """Map extracted data to Zoho Invoice format"""
        # Note: rate is usually in the base amount (converted to entity currency)
        rate = data.base_amount or data.amount or 0
        
        return {
            "customer_id": self.config.default_customer_id,
            "date": data.date,
            "line_items": [
                {
                    "name": data.description or "Expense Item",
                    "description": f"Ref: {data.transaction_no or 'N/A'}",
                    "rate": float(rate),
                    "quantity": 1
                }
            ],
            "notes": f"Sync from Expense Extraction Portal. Category: {data.sub_type or data.category}",
            "reference_number": data.transaction_no
        }

    def _map_to_expense(self, data: ReceiptData) -> Dict[str, Any]:
        """Map extracted data to Zoho Expense format"""
        amount = data.base_amount or data.amount or 0
        
        return {
            "account_id": self.config.default_vendor_id, # Re-using vendor_id as account_id for simplicity in config
            "date": data.date,
            "amount": float(amount),
            "description": data.description,
            "reference_number": data.transaction_no
        }

    async def create_invoice(self, data: ReceiptData) -> str:
        """Create an invoice in Zoho Books"""
        token = await self.get_valid_token()
        url = f"https://www.zohoapis.{self.config.dc_domain}/books/v3/invoices"
        
        params = {"organization_id": self.config.org_id}
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }
        
        payload = self._map_to_invoice(data)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, headers=headers, json=payload)
            if response.status_code in [201, 200]:
                res_data = response.json()
                invoice_id = res_data.get("invoice", {}).get("invoice_id")
                return invoice_id
            else:
                raise Exception(f"Zoho Invoice Creation Failed: {response.status_code} - {response.text}")
