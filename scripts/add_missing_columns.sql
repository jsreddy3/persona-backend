-- Migration script to add missing columns
-- This script will safely add missing columns if they don't exist

-- First, check if character_types column exists in characters table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_name = 'characters' AND column_name = 'character_types'
    ) THEN
        ALTER TABLE characters ADD COLUMN character_types JSONB DEFAULT '[]'::jsonb;
        RAISE NOTICE 'Added character_types column to characters table';
    ELSE
        RAISE NOTICE 'character_types column already exists in characters table';
    END IF;
END $$;

-- Next, check if last_chatted_with column exists in conversations table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_name = 'conversations' AND column_name = 'last_chatted_with'
    ) THEN
        ALTER TABLE conversations ADD COLUMN last_chatted_with TIMESTAMP;
        
        -- Initialize with updated_at values to maintain sorting order
        UPDATE conversations SET last_chatted_with = updated_at;
        
        RAISE NOTICE 'Added last_chatted_with column to conversations table';
    ELSE
        RAISE NOTICE 'last_chatted_with column already exists in conversations table';
    END IF;
END $$;

-- Verify the columns were added successfully
SELECT 
    table_name, 
    column_name, 
    data_type 
FROM 
    information_schema.columns 
WHERE 
    (table_name = 'characters' AND column_name = 'character_types') OR
    (table_name = 'conversations' AND column_name = 'last_chatted_with'); 