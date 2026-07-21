ALTER TABLE ws_projects ADD COLUMN close_reason TEXT;
ALTER TABLE ws_projects ADD COLUMN close_comments TEXT;

ALTER TABLE ws_projects ADD COLUMN competitor_company TEXT;
ALTER TABLE ws_projects ADD COLUMN competitor_type TEXT;
ALTER TABLE ws_projects ADD COLUMN competitor_brand TEXT;

ALTER TABLE ws_projects ADD COLUMN won_amount REAL;
ALTER TABLE ws_projects ADD COLUMN order_number TEXT;