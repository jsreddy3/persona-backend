-- Update message previews for all conversations
-- This will set the message_preview field for each conversation based on the most recent message
WITH latest_messages AS (
  SELECT DISTINCT ON (conversation_id)
    conversation_id,
    content,
    created_at
  FROM messages
  ORDER BY conversation_id, created_at DESC
)
UPDATE conversations c
SET message_preview = CASE 
    WHEN LENGTH(lm.content) > 30 THEN SUBSTRING(lm.content, 1, 30) || '...'
    ELSE lm.content
  END
FROM latest_messages lm
WHERE c.id = lm.conversation_id;

-- Output result
SELECT c.id, c.message_preview, c.last_chatted_with
FROM conversations c
ORDER BY c.last_chatted_with DESC NULLS LAST, c.created_at DESC
LIMIT 10; 