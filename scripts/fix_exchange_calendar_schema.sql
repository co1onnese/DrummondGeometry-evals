-- Migration: Fix exchange calendar country_code field length
-- Issue: Field is VARCHAR(2) but EODHD API returns "USA" (3 chars)
-- Solution: Increase to VARCHAR(3)

BEGIN;

-- Show current schema
SELECT
    'BEFORE MIGRATION:' as status,
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_name = 'exchanges'
  AND column_name = 'country_code';

-- Alter the column
ALTER TABLE exchanges
ALTER COLUMN country_code TYPE VARCHAR(3);

-- Show updated schema
SELECT
    'AFTER MIGRATION:' as status,
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_name = 'exchanges'
  AND column_name = 'country_code';

COMMIT;

-- Success message
SELECT 'Migration completed successfully!' as result;
