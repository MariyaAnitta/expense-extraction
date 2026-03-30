from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ReceiptData(BaseModel):
    date: Optional[str] = Field(None, description="Date of the transaction (YYYY-MM-DD)")
    description: Optional[str] = Field(None, description="Brief description of the expense")
    amount: Optional[float | str] = Field(None, description="Expense amount (debit)")
    deposit_amount: Optional[float | str] = Field(None, description="Deposit amount (credit)")
    currency: Optional[str] = Field("BHD", description="Currency of the transaction")
    received_by: Optional[str] = Field(None, description="Who received the payment (e.g., Biller name)")
    transaction_no: Optional[str] = Field(None, description="Reference or transaction number")
    phone_number: Optional[str] = Field(None, description="Phone number if applicable")
    bill_profile: Optional[str] = Field(None, description="Bill profile or account number")
    category: Optional[str] = Field("Expense", description="Type of transaction (Expense/Deposit)")
    confidence: float = Field(0.0, description="AI confidence score 0-100")
    remarks: Optional[str] = Field("ok", description="Additional remarks")

class ExtractionResult(BaseModel):
    file_id: str
    file_name: str
    status: str # PENDING, PROCESSING, COMPLETED, FAILED
    data: Optional[ReceiptData] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
