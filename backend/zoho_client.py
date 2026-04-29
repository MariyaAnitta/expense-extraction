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

    async def create_expense(self, data: ReceiptData) -> str:
        """Create an expense in Zoho Books with dynamic account routing"""
        token = await self.get_valid_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }
        params = {"organization_id": self.config.org_id}
        
        # 1. Fetch Chart of Accounts to resolve Petty_Cash correctly
        accounts_url = f"https://www.zohoapis.{self.config.dc_domain}/books/v3/chartofaccounts"
        
        account_id = ""
        paid_through_account_id = ""
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(accounts_url, params=params, headers=headers)
            if resp.status_code == 200:
                accounts = resp.json().get("chartofaccounts", [])
                
                # Check how Petty_Cash was created. If they created it as Expense, map it to account_id
                petty_exp = next((a for a in accounts if a["account_name"].lower() in ["petty_cash", "petty cash"] and "expense" in a["account_type"].lower()), None)
                
                if petty_exp:
                    account_id = petty_exp["account_id"]
                else:
                    # Fallback generic expense
                    exp = next((a for a in accounts if "expense" in a["account_type"].lower()), None)
                    if exp: account_id = exp["account_id"]
                
                # We need a bank or cash account for 'paid_through'
                # If they made Petty Cash as a bank/cash account, use it here instead!
                petty_cash = next((a for a in accounts if a["account_name"].lower() in ["petty_cash", "petty cash"] and a["account_type"].lower() in ["cash", "bank"]), None)
                if petty_cash:
                    paid_through_account_id = petty_cash["account_id"]
                else:
                    # Fallback to any generic bank/cash account
                    cash = next((a for a in accounts if a["account_type"].lower() in ["cash", "bank", "equity"]), None)
                    if cash: paid_through_account_id = cash["account_id"]
                    
        if not account_id:
             raise Exception("Failed to find a valid Expense Account in Zoho Chart of Accounts")
        if not paid_through_account_id:
             raise Exception("Failed to find a valid Cash/Bank Account (Paid Through) in Zoho Chart of Accounts")
             
        # Safely parse the amount, removing commas if necessary
        raw_amt = str(data.base_amount or data.amount or 0).replace(',', '')
        amount = float(raw_amt)
        
        # Safely parse date to strict YYYY-MM-DD format as required by Zoho
        zoho_date = ""
        try:
            if data.date:
                parsed = dateutil.parser.parse(data.date)
                zoho_date = parsed.strftime('%Y-%m-%d')
        except:
            pass
            
        payload = {
            "account_id": account_id,
            "paid_through_account_id": paid_through_account_id,
            "amount": amount,
            "description": f"{data.category or 'Expense'} - {data.description or 'Receipt'}",
            "reference_number": data.transaction_no or "Portal Sync"
        }
        
        # Only add date if valid, else Zoho falls back to today
        if zoho_date:
            payload["date"] = zoho_date

        # 2. Create the actual Expense record
        exp_url = f"https://www.zohoapis.{self.config.dc_domain}/books/v3/expenses"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(exp_url, params=params, headers=headers, json=payload)
            if response.status_code in [201, 200]:
                res_data = response.json()
                return res_data.get("expense", {}).get("expense_id")
            else:
                raise Exception(f"Zoho Expense Creation Failed: {response.status_code} - {response.text}")
