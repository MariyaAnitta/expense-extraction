import httpx
import time
import dateutil.parser
from typing import Optional, Dict, Any
from models import ReceiptData, ZohoConfig

class ZohoClient:
    def __init__(self, config: ZohoConfig):
        self.config = config
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        
    async def _refresh_access_token(self):
        """Exchange refresh token for a new access token"""
        accounts_url = f"https://accounts.{self.config.dc_domain}/oauth/v2/token"
        
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

    async def create_expense(self, data: ReceiptData) -> str:
        """Create an expense in Zoho Books with dynamic account routing and multi-currency support"""
        token = await self.get_valid_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }
        params = {"organization_id": self.config.org_id}
        
        # Resolve domains
        api_suffix = self.config.dc_domain.replace('zoho.', 'zohoapis.')
        base_url = f"https://www.{api_suffix}/books/v3"

        # 1. Fetch Chart of Accounts and Currencies in parallel
        async with httpx.AsyncClient() as client:
            # Get Accounts
            acc_resp = await client.get(f"{base_url}/chartofaccounts", params=params, headers=headers)
            accounts = acc_resp.json().get("chartofaccounts", []) if acc_resp.status_code == 200 else []
            
            # Get Currencies
            curr_resp = await client.get(f"{base_url}/settings/currencies", params=params, headers=headers)
            currencies = curr_resp.json().get("currencies", []) if curr_resp.status_code == 200 else []

            # Get Settings (to check base currency)
            settings_resp = await client.get(f"{base_url}/settings/organization", params=params, headers=headers)
            org_settings = settings_resp.json().get("organization", {}) if settings_resp.status_code == 200 else {}
            base_currency_code = org_settings.get("currency_code", "BHD")

        # 2. Map Expense Account
        account_id = ""
        target_name = (data.sub_type or data.category or "").lower().strip()
        
        # Try exact match first
        match = next((a for a in accounts if a["account_name"].lower().strip() == target_name and "expense" in a["account_type"].lower()), None)
        if not match:
            # Try fuzzy match (contains)
            match = next((a for a in accounts if target_name in a["account_name"].lower() and "expense" in a["account_type"].lower()), None)
        
        if match:
            account_id = match["account_id"]
        else:
            # Fallback to Petty_Cash or first generic expense
            petty_exp = next((a for a in accounts if a["account_name"].lower() in ["petty_cash", "petty cash"] and "expense" in a["account_type"].lower()), None)
            account_id = petty_exp["account_id"] if petty_exp else next((a["account_id"] for a in accounts if "expense" in a["account_type"].lower()), "")

        # 3. Map Paid Through Account (Bank/Cash)
        paid_through_account_id = ""
        petty_cash = next((a for a in accounts if a["account_name"].lower() in ["petty_cash", "petty cash"] and a["account_type"].lower() in ["cash", "bank"]), None)
        if petty_cash:
            paid_through_account_id = petty_cash["account_id"]
        else:
            cash = next((a for a in accounts if a["account_type"].lower() in ["cash", "bank", "equity"]), None)
            paid_through_account_id = cash["account_id"] if cash else ""

        if not account_id or not paid_through_account_id:
             raise Exception("Failed to resolve mandatory Zoho accounts (Expense/PaidThrough)")
             
        # 4. Handle Multi-Currency
        currency_id = ""
        exchange_rate = 1.0
        final_amount = 0.0
        
        record_currency = (data.currency or base_currency_code).upper()
        
        if record_currency != base_currency_code:
            # Find currency_id in Zoho
            z_curr = next((c for c in currencies if c["currency_code"] == record_currency), None)
            if z_curr:
                currency_id = z_curr["currency_id"]
                exchange_rate = float(data.exchange_rate or 1.0)
                final_amount = abs(float(str(data.amount or 0).replace(',', '')))
            else:
                # If currency not in Zoho, fallback to base currency conversion
                final_amount = abs(float(str(data.functional_amount or data.base_amount or 0).replace(',', '')))
        else:
            final_amount = abs(float(str(data.functional_amount or data.base_amount or 0).replace(',', '')))

        # 5. Build rich description
        desc_parts = []
        if data.sub_type and data.category and data.sub_type != data.category:
            desc_parts.append(f"{data.sub_type} ({data.category})")
        else:
            desc_parts.append(data.sub_type or data.category or "Expense")
            
        if data.description: desc_parts.append(data.description)
        if data.received_by: desc_parts.append(f"Vendor: {data.received_by}")
        if record_currency != base_currency_code:
            desc_parts.append(f"Original: {record_currency} {data.amount}")
        
        description = " | ".join(desc_parts)
            
        payload = {
            "account_id": account_id,
            "paid_through_account_id": paid_through_account_id,
            "amount": final_amount,
            "description": description,
            "reference_number": data.transaction_no or ""
        }
        
        if currency_id:
            payload["currency_id"] = currency_id
            payload["exchange_rate"] = exchange_rate

        # Safely parse date
        try:
            if data.date:
                parsed = dateutil.parser.parse(data.date)
                payload["date"] = parsed.strftime('%Y-%m-%d')
        except: pass

        # 7. Create Expense
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{base_url}/expenses", params=params, headers=headers, json=payload)
            if response.status_code in [201, 200]:
                return response.json().get("expense", {}).get("expense_id")
            else:
                raise Exception(f"Zoho Expense Creation Failed: {response.status_code} - {response.text}")

    async def attach_receipt(self, expense_id: str, image_url: str):
        """Download receipt from Supabase/URL and upload to Zoho as an attachment"""
        if not image_url or not expense_id or "manual" in image_url.lower():
            return
            
        token = await self.get_valid_token()
        api_suffix = self.config.dc_domain.replace('zoho.', 'zohoapis.')
        attach_url = f"https://www.{api_suffix}/books/v3/expenses/{expense_id}/receipt"
        
        params = {"organization_id": self.config.org_id}
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}
        
        try:
            async with httpx.AsyncClient() as client:
                # 1. Download the file from our storage
                file_resp = await client.get(image_url)
                if file_resp.status_code != 200:
                    print(f"Failed to download image for Zoho attach: {file_resp.status_code}")
                    return
                
                # 2. Extract filename from URL or default
                filename = image_url.split('/')[-1].split('?')[0] or "receipt.jpg"
                
                # 3. Upload to Zoho
                files = {
                    'receipt': (filename, file_resp.content)
                }
                
                # Note: Do NOT set Content-Type header manually for multipart uploads
                res = await client.post(attach_url, params=params, headers=headers, files=files)
                if res.status_code in [200, 201]:
                    print(f"Successfully attached receipt to Zoho expense {expense_id}")
                else:
                    print(f"Failed to attach receipt to Zoho: {res.status_code} - {res.text}")
                    
        except Exception as e:
            print(f"Error during Zoho receipt attachment: {e}")
