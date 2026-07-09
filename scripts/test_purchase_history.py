from app.services.purchase_history_service import PurchaseHistoryService

df = PurchaseHistoryService.get_history(
    customer="CARTONES AMERICA S.A.",
    family_id="5000",
    group_id="5110",
    months=18,
)

print(df)