ALTER TABLE anonymous_visitors
    ADD COLUMN IF NOT EXISTS trial_used_count INTEGER NOT NULL DEFAULT 0;

UPDATE anonymous_visitors
SET trial_used_count = 1
WHERE trial_used_at IS NOT NULL
  AND trial_used_count = 0;
