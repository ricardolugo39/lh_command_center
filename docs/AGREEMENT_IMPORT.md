# Agreement import foundation

Agreement imports accept `.xls` and `.xlsx` files up to 10 MB and 5,000 data
rows. The original extension and bytes are preserved. `openpyxl` reads `.xlsx`
and `xlrd` reads Excel 97-2003 `.xls`; both feed the same normalized parser
model. Content signatures select the reader, so table-based ERP exports saved
with an `.xls` extension are read through a table-only HTML adapter. Scripts,
styles, images, links, and forms are ignored. Macros and external code are not
executed, and `.xlsm` is rejected.

Unconfirmed imports live in `uploads/agreement-imports` behind a random token
for two hours. The server resolves all paths and verifies the token's customer
identifier. Confirmation reparses and revalidates the workbook. Successful,
cancelled, and expired imports remove their staged files.

Because the application has no authenticated-user model, tokens cannot yet be
bound to a user identity. Anyone who obtains a valid token URL during its
lifetime could access that staged import. Authentication and user ownership
must be added before exposing this workflow outside a trusted environment.

Confirmation claims the token before opening the business transaction. The
agreement, document metadata, and imported items commit atomically. A failed
operation resets the token and removes any final copied file. When an active
agreement exists, import is blocked until explicit replacement confirmation;
the prior record and items are retained with status `expired`.

Migration 9 is additive. All SKF-specific agreement-item columns remain
unchanged for legacy connectors. Generic fields live alongside them, and new
imports populate compatibility reference values required by the legacy schema.
