-- Add index membership tracking to market_symbols table
-- This allows tracking which indices (SP500, NASDAQ100, etc.) each symbol belongs to

-- Add index_membership column as TEXT array
ALTER TABLE market_symbols
ADD COLUMN IF NOT EXISTS index_membership TEXT[] DEFAULT '{}';

-- Add index for efficient filtering by index membership
CREATE INDEX IF NOT EXISTS idx_market_symbols_index_membership
    ON market_symbols USING GIN (index_membership);

-- Add comment for documentation
COMMENT ON COLUMN market_symbols.index_membership IS
    'Array of index names this symbol belongs to (e.g., {SP500, NASDAQ100})';
