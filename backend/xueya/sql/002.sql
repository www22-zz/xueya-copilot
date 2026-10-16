ALTER TABLE invocations ADD COLUMN usage_json TEXT;
ALTER TABLE invocations ADD COLUMN billing_status TEXT NOT NULL DEFAULT 'not_reported';